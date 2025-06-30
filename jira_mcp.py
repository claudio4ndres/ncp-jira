#!/usr/bin/env python3
"""
Servidor MCP para Jira API
Permite gestionar issues, projects, sprints y más desde Claude
"""

import asyncio
import json
import sys
import os
import base64
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError as e:
    print(f"❌ Error: MCP no está instalado. Ejecuta: uv add mcp", file=sys.stderr)
    sys.exit(1)

@dataclass
class JiraIssue:
    """Modelo de issue de Jira"""
    key: str
    summary: str
    status: str
    assignee: str
    priority: str
    issue_type: str
    created: str
    updated: str
    description: str = ""

@dataclass
class JiraProject:
    """Modelo de proyecto de Jira"""
    key: str
    name: str
    project_type: str
    lead: str

class JiraManager:
    """Gestor de API de Jira"""
    
    def __init__(self, jira_url: str, email: str, api_token: str):
        self.jira_url = jira_url.rstrip('/')
        self.email = email
        self.api_token = api_token
        
        # Crear autenticación básica
        auth_string = f"{email}:{api_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.headers = {
            "Authorization": f"Basic {auth_b64}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
    
    async def get_myself(self) -> Dict[str, Any]:
        """Obtener información del usuario actual"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/myself",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_projects(self) -> List[JiraProject]:
        """Obtener todos los proyectos"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/project",
                headers=self.headers
            )
            response.raise_for_status()
            projects_data = response.json()
            
            return [
                JiraProject(
                    key=project["key"],
                    name=project["name"],
                    project_type=project.get("projectTypeKey", "unknown"),
                    lead=project.get("lead", {}).get("displayName", "Sin asignar")
                )
                for project in projects_data
            ]
    
    async def search_issues(self, jql: str = None, assignee: str = None, project: str = None, max_results: int = 50) -> List[JiraIssue]:
        """Buscar issues con JQL o filtros"""
        
        # Construir JQL si no se proporciona
        if not jql:
            conditions = []
            if assignee:
                if assignee.lower() == "me":
                    conditions.append("assignee = currentUser()")
                else:
                    conditions.append(f"assignee = '{assignee}'")
            if project:
                conditions.append(f"project = '{project}'")
            
            jql = " AND ".join(conditions) if conditions else "order by updated DESC"
        
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,status,assignee,priority,issuetype,created,updated,description"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/search",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            issues = []
            for issue in data.get("issues", []):
                fields = issue["fields"]
                issues.append(JiraIssue(
                    key=issue["key"],
                    summary=fields.get("summary", "Sin título"),
                    status=fields.get("status", {}).get("name", "Desconocido"),
                    assignee=fields.get("assignee", {}).get("displayName", "Sin asignar") if fields.get("assignee") else "Sin asignar",
                    priority=fields.get("priority", {}).get("name", "Sin prioridad") if fields.get("priority") else "Sin prioridad",
                    issue_type=fields.get("issuetype", {}).get("name", "Desconocido"),
                    created=fields.get("created", ""),
                    updated=fields.get("updated", ""),
                    description=fields.get("description", {}).get("content", [{}])[0].get("content", [{}])[0].get("text", "") if fields.get("description") else ""
                ))
            
            return issues
    
    async def get_issue(self, issue_key: str) -> Optional[JiraIssue]:
        """Obtener un issue específico"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/issue/{issue_key}",
                headers=self.headers,
                params={"fields": "summary,status,assignee,priority,issuetype,created,updated,description"}
            )
            response.raise_for_status()
            issue = response.json()
            fields = issue["fields"]
            
            return JiraIssue(
                key=issue["key"],
                summary=fields.get("summary", "Sin título"),
                status=fields.get("status", {}).get("name", "Desconocido"),
                assignee=fields.get("assignee", {}).get("displayName", "Sin asignar") if fields.get("assignee") else "Sin asignar",
                priority=fields.get("priority", {}).get("name", "Sin prioridad") if fields.get("priority") else "Sin prioridad",
                issue_type=fields.get("issuetype", {}).get("name", "Desconocido"),
                created=fields.get("created", ""),
                updated=fields.get("updated", ""),
                description=fields.get("description", {}).get("content", [{}])[0].get("content", [{}])[0].get("text", "") if fields.get("description") else ""
            )
    
    async def create_issue(self, project_key: str, summary: str, description: str, issue_type: str = "Task") -> Dict[str, Any]:
        """Crear un nuevo issue"""
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                },
                "issuetype": {"name": issue_type}
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.jira_url}/rest/api/3/issue",
                headers=self.headers,
                json=issue_data
            )
            response.raise_for_status()
            return response.json()
    
    async def transition_issue(self, issue_key: str, transition_name: str) -> bool:
        """Cambiar estado de un issue"""
        # Primero obtener las transiciones disponibles
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions",
                headers=self.headers
            )
            response.raise_for_status()
            transitions = response.json().get("transitions", [])
            
            # Buscar la transición por nombre
            transition_id = None
            for transition in transitions:
                if transition["name"].lower() == transition_name.lower():
                    transition_id = transition["id"]
                    break
            
            if not transition_id:
                return False
            
            # Ejecutar la transición
            transition_data = {
                "transition": {"id": transition_id}
            }
            
            response = await client.post(
                f"{self.jira_url}/rest/api/3/issue/{issue_key}/transitions",
                headers=self.headers,
                json=transition_data
            )
            response.raise_for_status()
            return True
    
    async def assign_issue(self, issue_key: str, assignee: str) -> bool:
        """Asignar issue a un usuario"""
        assign_data = {
            "accountId": assignee if assignee != "me" else None
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.jira_url}/rest/api/3/issue/{issue_key}/assignee",
                headers=self.headers,
                json=assign_data
            )
            response.raise_for_status()
            return True

# Configuración desde variables de entorno
JIRA_URL = os.getenv("JIRA_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

if not all([JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
    print("❌ Error: Variables de entorno de Jira no configuradas", file=sys.stderr)
    print("Necesitas: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN", file=sys.stderr)
    sys.exit(1)

# Inicializar gestor de Jira
jira_manager = JiraManager(JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)
server = Server("jira")

@server.list_resources()
async def list_resources() -> List[types.Resource]:
    """Listar recursos disponibles de Jira"""
    return [
        types.Resource(
            uri="jira://my-issues",
            name="Mis Issues",
            description="Issues asignados a mí",
            mimeType="application/json",
        ),
        types.Resource(
            uri="jira://projects",
            name="Proyectos",
            description="Lista de proyectos de Jira",
            mimeType="application/json",
        ),
        types.Resource(
            uri="jira://recent-issues",
            name="Issues Recientes",
            description="Issues actualizados recientemente",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def read_resource(uri: str) -> str:
    """Leer contenido de recursos de Jira"""
    try:
        if uri == "jira://my-issues":
            issues = await jira_manager.search_issues(assignee="me", max_results=20)
            issues_data = [
                {
                    "key": issue.key,
                    "summary": issue.summary,
                    "status": issue.status,
                    "priority": issue.priority,
                    "type": issue.issue_type,
                    "updated": issue.updated
                }
                for issue in issues
            ]
            return json.dumps(issues_data, indent=2, ensure_ascii=False)
        
        elif uri == "jira://projects":
            projects = await jira_manager.get_projects()
            projects_data = [
                {
                    "key": project.key,
                    "name": project.name,
                    "type": project.project_type,
                    "lead": project.lead
                }
                for project in projects
            ]
            return json.dumps(projects_data, indent=2, ensure_ascii=False)
        
        elif uri == "jira://recent-issues":
            issues = await jira_manager.search_issues(jql="order by updated DESC", max_results=20)
            issues_data = [
                {
                    "key": issue.key,
                    "summary": issue.summary,
                    "status": issue.status,
                    "assignee": issue.assignee,
                    "updated": issue.updated
                }
                for issue in issues
            ]
            return json.dumps(issues_data, indent=2, ensure_ascii=False)
        
        else:
            raise ValueError(f"Recurso no encontrado: {uri}")
    
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@server.list_tools()
async def list_tools() -> List[types.Tool]:
    """Listar herramientas disponibles de Jira"""
    return [
        types.Tool(
            name="search_issues",
            description="Buscar issues con filtros o JQL",
            inputSchema={
                "type": "object",
                "properties": {
                    "jql": {"type": "string", "description": "Consulta JQL (opcional)"},
                    "assignee": {"type": "string", "description": "Usuario asignado (opcional, usa 'me' para ti)"},
                    "project": {"type": "string", "description": "Clave del proyecto (opcional)"},
                    "max_results": {"type": "integer", "description": "Máximo número de resultados (default: 20)"}
                }
            },
        ),
        types.Tool(
            name="get_issue",
            description="Obtener detalles de un issue específico",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Clave del issue (ej: PROJ-123)"}
                },
                "required": ["issue_key"]
            },
        ),
        types.Tool(
            name="create_issue",
            description="Crear un nuevo issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_key": {"type": "string", "description": "Clave del proyecto"},
                    "summary": {"type": "string", "description": "Título del issue"},
                    "description": {"type": "string", "description": "Descripción del issue"},
                    "issue_type": {"type": "string", "description": "Tipo de issue (Task, Bug, Story, etc.)"}
                },
                "required": ["project_key", "summary", "description"]
            },
        ),
        types.Tool(
            name="transition_issue",
            description="Cambiar estado de un issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string", "description": "Clave del issue"},
                    "transition": {"type": "string", "description": "Nuevo estado (In Progress, Done, etc.)"}
                },
                "required": ["issue_key", "transition"]
            },
        ),
        types.Tool(
            name="get_my_issues",
            description="Obtener todos mis issues asignados",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filtrar por estado (opcional)"}
                }
            },
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Ejecutar herramientas de Jira"""
    try:
        if name == "search_issues":
            jql = arguments.get("jql")
            assignee = arguments.get("assignee")
            project = arguments.get("project")
            max_results = arguments.get("max_results", 20)
            
            issues = await jira_manager.search_issues(jql, assignee, project, max_results)
            
            if not issues:
                return [types.TextContent(
                    type="text",
                    text="🔍 No se encontraron issues con esos criterios"
                )]
            
            result = f"🎫 **Issues encontrados:** ({len(issues)} resultados)\n\n"
            
            for issue in issues:
                result += f"🏷️ **{issue.key}** - {issue.summary}\n"
                result += f"   📊 Estado: {issue.status}\n"
                result += f"   👤 Asignado: {issue.assignee}\n"
                result += f"   🔥 Prioridad: {issue.priority}\n"
                result += f"   📅 Actualizado: {issue.updated[:10]}\n\n"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "get_issue":
            issue_key = arguments.get("issue_key")
            if not issue_key:
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requiere issue_key"
                )]
            
            issue = await jira_manager.get_issue(issue_key)
            if not issue:
                return [types.TextContent(
                    type="text",
                    text=f"❌ No se encontró el issue: {issue_key}"
                )]
            
            result = f"🎫 **{issue.key}** - {issue.summary}\n\n"
            result += f"📊 **Estado:** {issue.status}\n"
            result += f"👤 **Asignado:** {issue.assignee}\n"
            result += f"🔥 **Prioridad:** {issue.priority}\n"
            result += f"🏷️ **Tipo:** {issue.issue_type}\n"
            result += f"📅 **Creado:** {issue.created[:10]}\n"
            result += f"🔄 **Actualizado:** {issue.updated[:10]}\n\n"
            
            if issue.description:
                result += f"📝 **Descripción:**\n{issue.description}\n\n"
            
            result += f"🔗 **Ver en Jira:** {JIRA_URL}/browse/{issue.key}"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "create_issue":
            project_key = arguments.get("project_key")
            summary = arguments.get("summary")
            description = arguments.get("description")
            issue_type = arguments.get("issue_type", "Task")
            
            if not all([project_key, summary, description]):
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requieren project_key, summary y description"
                )]
            
            result = await jira_manager.create_issue(project_key, summary, description, issue_type)
            issue_key = result.get("key")
            
            return [types.TextContent(
                type="text",
                text=f"✅ Issue creado exitosamente!\n🎫 **{issue_key}** - {summary}\n🔗 Ver: {JIRA_URL}/browse/{issue_key}"
            )]
        
        elif name == "transition_issue":
            issue_key = arguments.get("issue_key")
            transition = arguments.get("transition")
            
            if not all([issue_key, transition]):
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requieren issue_key y transition"
                )]
            
            success = await jira_manager.transition_issue(issue_key, transition)
            
            if success:
                return [types.TextContent(
                    type="text",
                    text=f"✅ Issue {issue_key} movido a '{transition}' exitosamente"
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"❌ No se pudo mover {issue_key} a '{transition}'. Verifica que la transición sea válida."
                )]
        
        elif name == "get_my_issues":
            status_filter = arguments.get("status")
            jql = "assignee = currentUser()"
            
            if status_filter:
                jql += f" AND status = '{status_filter}'"
            
            jql += " ORDER BY updated DESC"
            
            issues = await jira_manager.search_issues(jql=jql, max_results=30)
            
            if not issues:
                return [types.TextContent(
                    type="text",
                    text="📋 No tienes issues asignados"
                )]
            
            result = f"📋 **Mis Issues:** ({len(issues)} total)\n\n"
            
            for issue in issues:
                result += f"🎫 **{issue.key}** - {issue.summary}\n"
                result += f"   📊 {issue.status} | 🔥 {issue.priority}\n\n"
            
            return [types.TextContent(type="text", text=result)]
        
        else:
            return [types.TextContent(
                type="text",
                text=f"❌ Herramienta desconocida: {name}"
            )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"❌ Error: {str(e)}"
        )]

async def main():
    """Función principal"""
    print("🎫 Inicializando servidor MCP para Jira...", file=sys.stderr)
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            print("✅ Conexión establecida con Claude", file=sys.stderr)
            
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="jira",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    ),
                ),
            )
    except Exception as e:
        print(f"❌ Error del servidor: {e}", file=sys.stderr)
        return 1
    
    return 0

if __name__ == "__main__":
    print("=" * 50, file=sys.stderr)
    print("🎫 MCP Jira Server", file=sys.stderr)
    print("🔌 Conecta Claude con Jira", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido por el usuario", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Error fatal: {e}", file=sys.stderr)
        sys.exit(1)
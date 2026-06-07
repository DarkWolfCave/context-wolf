"""
Infrastructure Management - SSH Hosts & Services
Handles adding, listing, and managing infrastructure hosts and services.

Architecture: Features Layer (depends on Core + Domain)
"""

import json
from typing import List, Dict, Optional, Tuple
from ..core.database import Database


class InfrastructureManager:
    """
    Manages infrastructure hosts and services.

    Responsibilities:
    - Add/Edit/Delete SSH hosts (with connection details)
    - Add/Edit/Delete services running on hosts
    - List hosts and services (global/project scope)
    - Show detailed host/service information

    Dependencies:
    - Database (core layer)
    """

    def __init__(self, database: Database):
        """
        Initialize InfrastructureManager.

        Args:
            database: Database instance
        """
        self.db = database
        self.conn = database.conn

    # ==================== HOST MANAGEMENT ====================

    def add_host(
        self,
        hostname: str,
        ip: str = None,
        port: int = 22,
        user: str = None,
        identity_file: str = None,
        location: str = None,
        provider: str = None,
        server_type: str = None,
        scope: str = 'global',
        project_name: str = None,
        tags: List[str] = None,
        comment: str = None
    ) -> int:
        """
        Add a new infrastructure host.

        Args:
            hostname: SSH hostname (e.g., 'prod-server-01')
            ip: IP address
            port: SSH port (default: 22)
            user: SSH user
            identity_file: Path to SSH key
            location: 'local' or 'extern'
            provider: Provider name (e.g., 'Netcup', 'AWS')
            server_type: Server type (e.g., 'VPS', 'Shared', 'Raspberry')
            scope: 'global' or 'project'
            project_name: Project name (for project scope)
            tags: List of tags
            comment: Additional comment

        Returns:
            Host ID

        Raises:
            ValueError: If hostname already exists or invalid scope
        """
        if scope not in ('global', 'project'):
            raise ValueError(f"Invalid scope: {scope}. Must be 'global' or 'project'")

        if location and location not in ('local', 'extern'):
            raise ValueError(f"Invalid location: {location}. Must be 'local' or 'extern'")

        # Get project_id if project scope
        project_id = None
        if scope == 'project':
            if not project_name:
                raise ValueError("project_name required for project scope")
            project_id = self.db.get_or_create_project(project_name)

        # Convert tags to JSON
        tags_json = json.dumps(tags) if tags else None

        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO infra_hosts (
                    hostname, ip, port, "user", identity_file,
                    location, provider, server_type,
                    scope, project_id, tags, comment
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (hostname, ip, port, user, identity_file, location, provider,
                  server_type, scope, project_id, tags_json, comment))

            result = cursor.fetchone()
            host_id = result['id'] if result else None
            self.conn.commit()
            return host_id

        except Exception as e:
            self.conn.rollback()
            error_msg = str(e).lower()

            if 'duplicate key' in error_msg:
                raise ValueError(f"Host '{hostname}' already exists")

            if 'statement timeout' in error_msg or 'canceling statement' in error_msg:
                raise RuntimeError(
                    f"Database operation timed out (>10s). "
                    f"This usually means a lock conflict with another process. "
                    f"Please try again in a moment."
                )

            raise

        finally:
            cursor.close()

    def list_hosts(
        self,
        scope: str = None,
        location: str = None,
        project_name: str = None,
        tags: List[str] = None,
        minimal: bool = False
    ) -> List[Dict]:
        """
        List infrastructure hosts with optional filtering.

        Args:
            scope: Filter by scope ('global', 'project', or None for all)
            location: Filter by location ('local', 'extern')
            project_name: Filter by project name
            tags: Filter by tags (AND logic)
            minimal: Return minimal data (hostname, location, tags only)

        Returns:
            List of host dictionaries
        """
        cursor = self.conn.cursor()

        # Build query
        where_clauses = []
        params = []

        if scope:
            where_clauses.append("h.scope = %s")
            params.append(scope)

        if location:
            where_clauses.append("h.location = %s")
            params.append(location)

        if project_name:
            where_clauses.append("p.name = %s")
            params.append(project_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if minimal:
            sql = f"""
                SELECT h.hostname, h.location, h.tags, h.server_type, h.provider
                FROM infra_hosts h
                LEFT JOIN projects p ON h.project_id = p.id
                {where_sql}
                ORDER BY h.hostname
            """
        else:
            sql = f"""
                SELECT h.*, p.name as project_name
                FROM infra_hosts h
                LEFT JOIN projects p ON h.project_id = p.id
                {where_sql}
                ORDER BY h.hostname
            """

        cursor.execute(sql, params)
        results = []

        for row in cursor.fetchall():
            host_dict = dict(row)

            # Parse tags JSON
            if host_dict.get('tags'):
                try:
                    host_dict['tags'] = json.loads(host_dict['tags'])
                except Exception:
                    host_dict['tags'] = []

            # Filter by tags if specified
            if tags:
                host_tags = host_dict.get('tags', [])
                if not all(tag in host_tags for tag in tags):
                    continue

            results.append(host_dict)

        cursor.close()
        return results

    def show_host(self, hostname: str) -> Optional[Dict]:
        """
        Get detailed information about a specific host.

        Args:
            hostname: Hostname to show

        Returns:
            Host dictionary with services, or None if not found
        """
        cursor = self.conn.cursor()

        # Get host details
        cursor.execute("""
            SELECT h.*, p.name as project_name
            FROM infra_hosts h
            LEFT JOIN projects p ON h.project_id = p.id
            WHERE h.hostname = %s
        """, (hostname,))

        result = cursor.fetchone()
        if not result:
            cursor.close()
            return None

        host_dict = dict(result)

        # Parse tags
        if host_dict.get('tags'):
            try:
                host_dict['tags'] = json.loads(host_dict['tags'])
            except Exception:
                host_dict['tags'] = []

        # Get services for this host
        cursor.execute("""
            SELECT * FROM infra_services
            WHERE host_id = %s
            ORDER BY env, service_name
        """, (host_dict['id'],))

        services = []
        for row in cursor.fetchall():
            service_dict = dict(row)
            if service_dict.get('tags'):
                try:
                    service_dict['tags'] = json.loads(service_dict['tags'])
                except Exception:
                    service_dict['tags'] = []
            services.append(service_dict)

        host_dict['services'] = services
        cursor.close()
        return host_dict

    def edit_host(
        self,
        hostname: str,
        ip: str = None,
        port: int = None,
        user: str = None,
        identity_file: str = None,
        location: str = None,
        provider: str = None,
        server_type: str = None,
        tags: List[str] = None,
        comment: str = None
    ) -> bool:
        """
        Edit an existing host.

        Args:
            hostname: Hostname to edit
            **kwargs: Fields to update (None values are skipped)

        Returns:
            True if updated, False if host not found
        """
        # Build update query dynamically
        updates = []
        params = []

        if ip is not None:
            updates.append('ip = %s')
            params.append(ip)

        if port is not None:
            updates.append('port = %s')
            params.append(port)

        if user is not None:
            updates.append('"user" = %s')
            params.append(user)

        if identity_file is not None:
            updates.append('identity_file = %s')
            params.append(identity_file)

        if location is not None:
            if location not in ('local', 'extern'):
                raise ValueError(f"Invalid location: {location}")
            updates.append('location = %s')
            params.append(location)

        if provider is not None:
            updates.append('provider = %s')
            params.append(provider)

        if server_type is not None:
            updates.append('server_type = %s')
            params.append(server_type)

        if tags is not None:
            updates.append('tags = %s')
            params.append(json.dumps(tags))

        if comment is not None:
            updates.append('comment = %s')
            params.append(comment)

        if not updates:
            return False

        # Always update updated_at
        updates.append('updated_at = EXTRACT(EPOCH FROM NOW())::BIGINT')

        cursor = self.conn.cursor()
        try:
            params.append(hostname)
            sql = f"""
                UPDATE infra_hosts
                SET {', '.join(updates)}
                WHERE hostname = %s
            """
            cursor.execute(sql, params)
            affected = cursor.rowcount
            self.conn.commit()
            return affected > 0

        finally:
            cursor.close()

    def delete_host(self, hostname: str, force: bool = False) -> Tuple[bool, str]:
        """
        Delete a host.

        Args:
            hostname: Hostname to delete
            force: Force deletion even if services exist

        Returns:
            (success: bool, message: str)
        """
        cursor = self.conn.cursor()

        try:
            # Check if host exists
            cursor.execute("SELECT id FROM infra_hosts WHERE hostname = %s", (hostname,))
            result = cursor.fetchone()
            if not result:
                return False, f"Host '{hostname}' not found"

            host_id = result['id']

            # Check for services
            cursor.execute("SELECT COUNT(*) AS cnt FROM infra_services WHERE host_id = %s", (host_id,))
            service_count = cursor.fetchone()['cnt']

            if service_count > 0 and not force:
                return False, f"Host has {service_count} service(s). Use --force to delete anyway."

            # Delete host (CASCADE will delete services)
            cursor.execute("DELETE FROM infra_hosts WHERE hostname = %s", (hostname,))
            self.conn.commit()

            msg = f"Deleted host '{hostname}'"
            if service_count > 0:
                msg += f" and {service_count} service(s)"

            return True, msg

        except Exception as e:
            self.conn.rollback()
            return False, f"Error deleting host: {e}"

        finally:
            cursor.close()

    # ==================== SERVICE MANAGEMENT ====================

    def add_service(
        self,
        hostname: str,
        service_name: str,
        env: str = None,
        app_path: str = None,
        service_type: str = None,
        deploy_method: str = None,
        health_url: str = None,
        scope: str = 'project',
        project_name: str = None,
        tags: List[str] = None,
        comment: str = None
    ) -> int:
        """
        Add a service to a host.

        Args:
            hostname: Host where service runs
            service_name: Service name
            env: Environment ('prod', 'staging', 'dev', 'test')
            app_path: Application path on host
            service_type: Service type (e.g., 'docker', 'systemd', 'pm2')
            deploy_method: Deployment method
            health_url: Health check URL
            scope: 'global' or 'project'
            project_name: Project name (for project scope)
            tags: List of tags
            comment: Additional comment

        Returns:
            Service ID
        """
        cursor = self.conn.cursor()

        try:
            # Get host_id
            cursor.execute("SELECT id FROM infra_hosts WHERE hostname = %s", (hostname,))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Host '{hostname}' not found")

            host_id = result['id']

            # Get project_id if project scope
            project_id = None
            if scope == 'project':
                if not project_name:
                    raise ValueError("project_name required for project scope")
                project_id = self.db.get_or_create_project(project_name)

            # Validate env
            if env and env not in ('prod', 'staging', 'dev', 'test'):
                raise ValueError(f"Invalid env: {env}")

            tags_json = json.dumps(tags) if tags else None

            cursor.execute("""
                INSERT INTO infra_services (
                    host_id, service_name, env, app_path,
                    service_type, deploy_method, health_url,
                    scope, project_id, tags, comment
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (host_id, service_name, env, app_path, service_type,
                  deploy_method, health_url, scope, project_id, tags_json, comment))

            result = cursor.fetchone()
            service_id = result['id'] if result else None
            self.conn.commit()
            return service_id

        except Exception as e:
            self.conn.rollback()
            error_msg = str(e).lower()

            if 'duplicate key' in error_msg:
                raise ValueError(f"Service '{service_name}' already exists on host '{hostname}'")

            if 'statement timeout' in error_msg or 'canceling statement' in error_msg:
                raise RuntimeError(
                    f"Database operation timed out (>10s). "
                    f"This usually means a lock conflict with another process. "
                    f"Please try again in a moment."
                )

            raise

        finally:
            cursor.close()

    def list_services(
        self,
        hostname: str = None,
        env: str = None,
        scope: str = None,
        project_name: str = None
    ) -> List[Dict]:
        """
        List services with optional filtering.

        Args:
            hostname: Filter by host
            env: Filter by environment
            scope: Filter by scope
            project_name: Filter by project

        Returns:
            List of service dictionaries
        """
        cursor = self.conn.cursor()

        where_clauses = []
        params = []

        if hostname:
            where_clauses.append("h.hostname = %s")
            params.append(hostname)

        if env:
            where_clauses.append("s.env = %s")
            params.append(env)

        if scope:
            where_clauses.append("s.scope = %s")
            params.append(scope)

        if project_name:
            where_clauses.append("p.name = %s")
            params.append(project_name)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
            SELECT s.*, h.hostname, p.name as project_name
            FROM infra_services s
            JOIN infra_hosts h ON s.host_id = h.id
            LEFT JOIN projects p ON s.project_id = p.id
            {where_sql}
            ORDER BY h.hostname, s.env, s.service_name
        """

        cursor.execute(sql, params)
        results = []

        for row in cursor.fetchall():
            service_dict = dict(row)
            if service_dict.get('tags'):
                try:
                    service_dict['tags'] = json.loads(service_dict['tags'])
                except Exception:
                    service_dict['tags'] = []
            results.append(service_dict)

        cursor.close()
        return results

    def edit_service(
        self,
        hostname: str,
        service_name: str,
        env: str = None,
        app_path: str = None,
        service_type: str = None,
        deploy_method: str = None,
        health_url: str = None,
        tags: List[str] = None,
        comment: str = None
    ) -> bool:
        """
        Edit an existing service.

        Args:
            hostname: Hostname where service runs
            service_name: Service name to edit
            env: Environment ('prod', 'staging', 'dev', 'test')
            app_path: Application path on host
            service_type: Service type (e.g., 'docker', 'systemd', 'pm2')
            deploy_method: Deployment method (e.g., 'ssh', 'local')
            health_url: Health check URL
            tags: List of tags
            comment: Additional comment

        Returns:
            True if updated, False if service not found
        """
        # Build update query dynamically
        updates = []
        params = []

        if env is not None:
            if env not in ('prod', 'staging', 'dev', 'test'):
                raise ValueError(f"Invalid env: {env}")
            updates.append('env = %s')
            params.append(env)

        if app_path is not None:
            updates.append('app_path = %s')
            params.append(app_path)

        if service_type is not None:
            updates.append('service_type = %s')
            params.append(service_type)

        if deploy_method is not None:
            updates.append('deploy_method = %s')
            params.append(deploy_method)

        if health_url is not None:
            updates.append('health_url = %s')
            params.append(health_url)

        if tags is not None:
            updates.append('tags = %s')
            params.append(json.dumps(tags))

        if comment is not None:
            updates.append('comment = %s')
            params.append(comment)

        if not updates:
            return False

        # Always update updated_at
        updates.append('updated_at = EXTRACT(EPOCH FROM NOW())::BIGINT')

        cursor = self.conn.cursor()
        try:
            params.extend([hostname, service_name])
            sql = f"""
                UPDATE infra_services
                SET {', '.join(updates)}
                WHERE host_id = (SELECT id FROM infra_hosts WHERE hostname = %s)
                AND service_name = %s
            """
            cursor.execute(sql, params)
            affected = cursor.rowcount
            self.conn.commit()
            return affected > 0

        finally:
            cursor.close()

    def delete_service(self, hostname: str, service_name: str) -> Tuple[bool, str]:
        """
        Delete a service.

        Args:
            hostname: Host name
            service_name: Service name to delete

        Returns:
            (success: bool, message: str)
        """
        cursor = self.conn.cursor()

        try:
            cursor.execute("""
                DELETE FROM infra_services
                WHERE host_id = (SELECT id FROM infra_hosts WHERE hostname = %s)
                AND service_name = %s
            """, (hostname, service_name))

            if cursor.rowcount > 0:
                self.conn.commit()
                return True, f"Deleted service '{service_name}' from host '{hostname}'"
            else:
                return False, f"Service '{service_name}' not found on host '{hostname}'"

        except Exception as e:
            self.conn.rollback()
            return False, f"Error deleting service: {e}"

        finally:
            cursor.close()

    # ==================== SEARCH ====================

    def search(self, query: str, limit: int = 10) -> Dict[str, List[Dict]]:
        """
        Search across hosts and services.

        Searches in: hostname, service_name, comment, tags, server_type, service_type
        Supports multi-word queries (all words must match in any field).

        Args:
            query: Search term (single word or multiple words)
            limit: Max results per category

        Returns:
            Dictionary with 'hosts' and 'services' lists
        """
        if not query or not query.strip():
            return {'hosts': [], 'services': []}

        cursor = self.conn.cursor()

        # Split query into words for multi-word support
        words = query.lower().split()

        results = {'hosts': [], 'services': []}

        try:
            # Build multi-word search: each word must match in ANY field
            # Concatenate all searchable fields for each word check
            host_word_conditions = []
            host_params = []
            for word in words:
                word_pattern = f"%{word}%"
                host_word_conditions.append("""
                    (LOWER(h.hostname) LIKE %s
                     OR LOWER(COALESCE(h.comment, '')) LIKE %s
                     OR LOWER(COALESCE(h.tags, '')) LIKE %s
                     OR LOWER(COALESCE(h.server_type, '')) LIKE %s
                     OR LOWER(COALESCE(h.provider, '')) LIKE %s)
                """)
                host_params.extend([word_pattern] * 5)

            # Add ORDER BY params (use first word for ranking)
            first_word_pattern = f"%{words[0]}%"
            host_params.append(first_word_pattern)
            host_params.append(limit)

            host_where = " AND ".join(host_word_conditions)
            cursor.execute(f"""
                SELECT h.*, p.name as project_name
                FROM infra_hosts h
                LEFT JOIN projects p ON h.project_id = p.id
                WHERE {host_where}
                ORDER BY
                    CASE WHEN LOWER(h.hostname) LIKE %s THEN 0 ELSE 1 END,
                    h.hostname
                LIMIT %s
            """, host_params)

            for row in cursor.fetchall():
                host_dict = dict(row)
                if host_dict.get('tags'):
                    try:
                        host_dict['tags'] = json.loads(host_dict['tags'])
                    except Exception:
                        host_dict['tags'] = []
                results['hosts'].append(host_dict)

            # Search services with multi-word support
            svc_word_conditions = []
            svc_params = []
            for word in words:
                word_pattern = f"%{word}%"
                svc_word_conditions.append("""
                    (LOWER(s.service_name) LIKE %s
                     OR LOWER(COALESCE(s.comment, '')) LIKE %s
                     OR LOWER(COALESCE(s.tags, '')) LIKE %s
                     OR LOWER(COALESCE(s.service_type, '')) LIKE %s
                     OR LOWER(h.hostname) LIKE %s)
                """)
                svc_params.extend([word_pattern] * 5)

            svc_params.append(first_word_pattern)
            svc_params.append(limit)

            svc_where = " AND ".join(svc_word_conditions)
            cursor.execute(f"""
                SELECT s.*, h.hostname, p.name as project_name
                FROM infra_services s
                JOIN infra_hosts h ON s.host_id = h.id
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE {svc_where}
                ORDER BY
                    CASE WHEN LOWER(s.service_name) LIKE %s THEN 0 ELSE 1 END,
                    h.hostname, s.service_name
                LIMIT %s
            """, svc_params)

            for row in cursor.fetchall():
                service_dict = dict(row)
                if service_dict.get('tags'):
                    try:
                        service_dict['tags'] = json.loads(service_dict['tags'])
                    except Exception:
                        service_dict['tags'] = []
                results['services'].append(service_dict)

            return results

        finally:
            cursor.close()

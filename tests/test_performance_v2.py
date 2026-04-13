#!/usr/bin/env python3
"""Performance Test für Context Manager V2"""

import time
import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from context_manager_v2 import ContextManagerV2

def generate_test_content(index):
    """Generiere realistischen Test-Content"""
    templates = [
        "Implemented {feature} with {tech} for better {benefit}",
        "Fixed {issue} in {module} that was causing {problem}",
        "Refactored {component} to use {pattern} pattern",
        "Added {test} tests for {module} with {coverage}% coverage",
        "Optimized {function} reducing runtime from {old}ms to {new}ms",
        "Documented {api} endpoints with {format} format",
        "Migrated {service} from {old_tech} to {new_tech}",
        "Resolved {type} vulnerability in {package} dependency",
        "Deployed {feature} to {environment} environment successfully",
        "Updated {config} configuration for {purpose}"
    ]

    features = ['authentication', 'payment processing', 'search functionality',
                'user dashboard', 'API gateway', 'caching layer', 'database indexing']
    techs = ['React', 'Node.js', 'PostgreSQL', 'Redis', 'Docker', 'Kubernetes',
             'GraphQL', 'REST API', 'WebSockets', 'JWT']
    modules = ['auth', 'user', 'payment', 'notification', 'analytics', 'admin',
               'report', 'export', 'import', 'sync']

    template = random.choice(templates)
    content = template.format(
        feature=random.choice(features),
        tech=random.choice(techs),
        benefit=random.choice(['performance', 'scalability', 'security', 'usability']),
        issue=f"bug-{random.randint(100,999)}",
        module=random.choice(modules),
        problem=random.choice(['memory leak', 'slow queries', 'race condition']),
        component=random.choice(modules),
        pattern=random.choice(['factory', 'singleton', 'observer', 'strategy']),
        test=random.choice(['unit', 'integration', 'e2e', 'performance']),
        coverage=random.randint(70, 99),
        function=f"{random.choice(['get', 'update', 'delete', 'process'])}_{random.choice(modules)}",
        old=random.randint(500, 5000),
        new=random.randint(10, 499),
        api=f"/api/v{random.randint(1,3)}/{random.choice(modules)}",
        format=random.choice(['OpenAPI', 'Swagger', 'RAML']),
        service=random.choice(modules),
        old_tech=random.choice(['MySQL', 'MongoDB', 'REST', 'SOAP']),
        new_tech=random.choice(['PostgreSQL', 'Redis', 'GraphQL', 'gRPC']),
        type=random.choice(['XSS', 'SQL Injection', 'CSRF', 'XXE']),
        package=random.choice(['lodash', 'axios', 'express', 'jsonwebtoken']),
        environment=random.choice(['staging', 'production', 'development']),
        config=random.choice(['nginx', 'docker', 'kubernetes', 'webpack']),
        purpose=random.choice(['performance tuning', 'security hardening', 'load balancing'])
    )

    # Füge längeren Text für realistischere Größe hinzu
    details = f"""
    Entry #{index}: {content}

    Additional context for this change:
    - Impact: This change affects multiple components in the system
    - Testing: Comprehensive tests have been added to ensure stability
    - Documentation: Updated relevant documentation and README files
    - Review: Code reviewed by team members and approved
    - Metrics: Performance metrics show {random.randint(10,50)}% improvement
    """

    return details

def test_performance(test_size):
    """Führe Performance-Test mit gegebener Anzahl Einträge durch"""

    print(f"\n{'='*60}")
    print(f"🚀 PERFORMANCE TEST MIT {test_size:,} EINTRÄGEN")
    print(f"{'='*60}\n")

    # Neuer Context Manager mit Test-DB
    db_path = Path.home() / '.context' / f'test_v2_{test_size}.db'
    db_path.unlink(missing_ok=True)  # Lösche alte Test-DB

    cm = ContextManagerV2(str(db_path))

    # Test 1: INSERT Performance
    print(f"📝 Test 1: Füge {test_size:,} Einträge hinzu...")
    start = time.time()

    # Verschiedene Projekte für realistischen Test
    projects = [f'project-{i}' for i in range(max(1, test_size // 100))]
    types = ['code', 'fix', 'feature', 'doc', 'test', 'refactor']

    for i in range(test_size):
        content = generate_test_content(i)
        cm.save(
            content,
            type=random.choice(types),
            project=random.choice(projects)
        )

        # Progress indicator
        if i > 0 and i % 100 == 0:
            elapsed = time.time() - start
            rate = i / elapsed
            eta = (test_size - i) / rate
            print(f"  Progress: {i:,}/{test_size:,} ({i*100/test_size:.1f}%) - "
                  f"Rate: {rate:.0f}/s - ETA: {eta:.0f}s", end='\r')

    insert_time = time.time() - start
    print(f"\n✅ INSERT Zeit: {insert_time:.2f}s ({test_size/insert_time:.0f} ops/s)")
    print(f"   Durchschnitt: {insert_time/test_size*1000:.2f}ms pro INSERT")

    # Test 2: SEARCH Performance
    print(f"\n🔍 Test 2: Search Performance...")

    search_queries = [
        "authentication", "performance", "bug", "refactor",
        "PostgreSQL", "Docker", "security", "optimization",
        "fixed memory leak", "implemented feature"
    ]

    search_times = []
    for query in search_queries:
        start = time.time()
        results = cm.search(query, limit=50)
        search_time = (time.time() - start) * 1000
        search_times.append(search_time)
        print(f"  Query '{query}': {search_time:.2f}ms, {len(results)} Ergebnisse")

    avg_search = sum(search_times) / len(search_times)
    print(f"✅ Durchschnittliche Suchzeit: {avg_search:.2f}ms")

    # Test 3: PROJECT LIST Performance
    print(f"\n📚 Test 4: Project Liste Performance...")
    start = time.time()
    projects = cm.list_projects()
    list_time = (time.time() - start) * 1000
    print(f"✅ Liste von {len(projects)} Projekten: {list_time:.2f}ms")

    # Test 5: STATS Performance
    print(f"\n📊 Test 5: Statistiken Performance...")
    start = time.time()
    stats = cm.get_stats()
    stats_time = (time.time() - start) * 1000
    print(f"✅ Statistiken abrufen: {stats_time:.2f}ms")
    print(f"   DB Größe: {stats['db_size'] / 1024 / 1024:.1f} MB")
    print(f"   Aktionen: {stats['actions']:,}")
    print(f"   Projekte: {stats['projects']}")

    # Test 6: VACUUM Performance
    print(f"\n🧹 Test 6: Vacuum/Optimize Performance...")
    start = time.time()
    cm.vacuum()
    vacuum_time = (time.time() - start) * 1000
    print(f"✅ Datenbank optimiert: {vacuum_time:.2f}ms")

    # Zusammenfassung
    print(f"\n{'='*60}")
    print(f"📈 ZUSAMMENFASSUNG für {test_size:,} Einträge:")
    print(f"{'='*60}")
    print(f"• INSERT:  {insert_time:.2f}s total, {insert_time/test_size*1000:.2f}ms/op")
    print(f"• SEARCH:  {avg_search:.2f}ms durchschnitt")
    print(f"• CHECK:   {avg_check:.2f}ms durchschnitt")
    print(f"• LIST:    {list_time:.2f}ms")
    print(f"• STATS:   {stats_time:.2f}ms")
    print(f"• VACUUM:  {vacuum_time:.2f}ms")
    print(f"• DB Size: {stats['db_size'] / 1024 / 1024:.1f} MB")
    print(f"{'='*60}")

    # Cleanup
    if test_size <= 1000:  # Behalte größere DBs für weitere Tests
        db_path.unlink(missing_ok=True)

    return {
        'insert_time': insert_time,
        'avg_search': avg_search,
        'avg_check': avg_check,
        'db_size_mb': stats['db_size'] / 1024 / 1024
    }

if __name__ == "__main__":
    # Kleine Tests zum Aufwärmen
    print("🔥 Warming up with small test...")
    test_performance(100)

    # Test mit 1.000 Einträgen
    print("\n" + "="*80)
    print("🎯 TEST MIT 1.000 EINTRÄGEN")
    print("="*80)
    results_1k = test_performance(1000)

    # Test mit 10.000 Einträgen
    print("\n" + "="*80)
    print("🚀 TEST MIT 10.000 EINTRÄGEN")
    print("="*80)
    results_10k = test_performance(10000)

    # Vergleich
    print("\n" + "="*80)
    print("📊 SKALIERUNGS-VERGLEICH")
    print("="*80)
    print(f"{'Metrik':<20} {'1K Einträge':>15} {'10K Einträge':>15} {'Faktor':>10}")
    print("-"*60)
    print(f"{'INSERT total':<20} {results_1k['insert_time']:>14.2f}s {results_10k['insert_time']:>14.2f}s "
          f"{results_10k['insert_time']/results_1k['insert_time']:>9.1f}x")
    print(f"{'SEARCH avg':<20} {results_1k['avg_search']:>13.2f}ms {results_10k['avg_search']:>13.2f}ms "
          f"{results_10k['avg_search']/results_1k['avg_search']:>9.1f}x")
    print(f"{'CHECK avg':<20} {results_1k['avg_check']:>13.2f}ms {results_10k['avg_check']:>13.2f}ms "
          f"{results_10k['avg_check']/results_1k['avg_check']:>9.1f}x")
    print(f"{'DB Size':<20} {results_1k['db_size_mb']:>13.1f}MB {results_10k['db_size_mb']:>13.1f}MB "
          f"{results_10k['db_size_mb']/results_1k['db_size_mb']:>9.1f}x")
    print("="*80)

    # Hochrechnung
    print("\n🔮 HOCHRECHNUNG auf größere Datenmengen:")
    print(f"• 100K Einträge: ~{results_10k['avg_search'] * 2:.0f}ms Suche, "
          f"~{results_10k['db_size_mb'] * 10:.0f}MB")
    print(f"• 1M Einträge:   ~{results_10k['avg_search'] * 5:.0f}ms Suche, "
          f"~{results_10k['db_size_mb'] * 100:.0f}MB")
    print("\n✅ Test abgeschlossen!")
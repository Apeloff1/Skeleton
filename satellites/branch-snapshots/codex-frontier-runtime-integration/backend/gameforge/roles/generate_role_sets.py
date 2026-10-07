#!/usr/bin/env python3
"""
Role Set Generator for GameForge CNS
Generates high-quality 100-role sets for major room categories.
"""

import json
from pathlib import Path
from typing import List, Dict

def create_role(role_id: str, name: str, category: str, specialty: str, 
                perspective: str, traits: List[str], skills: List[str],
                prompt_template: str, quality_criteria: List[str], weight: float = 1.0) -> Dict:
    return {
        "role_id": role_id,
        "name": name,
        "category": category,
        "specialty": specialty,
        "perspective": perspective,
        "traits": traits,
        "skills": skills,
        "prompt_template": prompt_template,
        "quality_criteria": quality_criteria,
        "weight": weight
    }

def generate_research_roles() -> List[Dict]:
    """Generate high-quality roles for Research rooms."""
    roles = []
    base_traits = ["analytical", "curious", "thorough"]
    
    research_specialties = [
        ("Literature Review Specialist", "Academic and industry papers", "Focuses on existing knowledge and identifying gaps"),
        ("Data Pattern Analyst", "Finding statistical and behavioral patterns", "Sees hidden correlations others miss"),
        ("Hypothesis Generator", "Creating testable ideas from observations", "Turns raw data into promising research directions"),
        ("Methodology Expert", "Research design and validity", "Ensures studies are rigorous and unbiased"),
        ("Competitor Intelligence Analyst", "What others are building and why", "Understands strategic implications of competitor moves"),
        ("Player Behavior Researcher", "How players actually interact with systems", "Grounds design in real player data"),
        ("Trend Forecaster", "Where the industry is heading", "Identifies emerging patterns before they become obvious"),
        ("Systems Thinking Researcher", "How different game systems interact", "Sees second and third-order effects"),
        ("Narrative Impact Analyst", "How stories affect player psychology", "Measures emotional and cognitive impact of narrative"),
        ("Monetization Ethics Researcher", "Long-term effects of monetization on players", "Studies sustainable vs extractive models"),
        ("Accessibility Researcher", "How design affects different player groups", "Ensures games work for diverse audiences"),
        ("Community Health Analyst", "Long-term effects on player communities", "Studies toxicity, retention, and social dynamics"),
        ("Technical Feasibility Researcher", "What is actually buildable", "Bridges vision with engineering reality"),
        ("Historical Context Specialist", "How similar problems were solved before", "Learns from past successes and failures"),
        ("Cross-Platform Behavior Analyst", "How players behave differently across platforms", "Identifies platform-specific patterns"),
        ("Retention Science Specialist", "What actually keeps players coming back", "Data-driven understanding of long-term engagement"),
        ("Innovation Pattern Researcher", "How breakthroughs happen in games", "Studies the conditions that enable real innovation"),
        ("Risk Assessment Analyst", "What could go wrong and how bad", "Quantifies and prioritizes potential failure modes"),
        ("Knowledge Synthesis Expert", "Connecting insights across domains", "Finds unexpected connections between different fields"),
        ("Ethical Impact Researcher", "Long-term societal effects of game design", "Considers broader implications beyond the game")
    ]
    
    for i, (name, specialty, perspective) in enumerate(research_specialties, 1):
        roles.append(create_role(
            role_id=f"research_{i:03d}",
            name=name,
            category="research",
            specialty=specialty,
            perspective=perspective,
            traits=base_traits + ["evidence-based"],
            skills=["research methodology", "critical analysis", "synthesis"],
            prompt_template=f"You are a {name}. {perspective}. Analyze the current work through this lens and provide evidence-based insights.",
            quality_criteria=["evidence-based", "actionable insights", "well-researched"],
            weight=1.0
        ))
    
    additional_focuses = [
        "Player Psychology", "Game Systems", "Narrative Design", "Live Operations",
        "Monetization", "Community", "Technical Architecture", "Market Analysis",
        "Trend Analysis", "Competitive Intelligence", "Player Segmentation",
        "Engagement Metrics", "Churn Prediction", "Feature Impact", "A/B Test Design",
        "Qualitative Research", "Quantitative Analysis", "Mixed Methods", "Ethnographic Study",
        "Diary Study Analysis", "Usability Testing", "Playtest Synthesis", "Data Visualization",
        "Statistical Modeling", "Machine Learning Applications", "Predictive Analytics",
        "Causal Inference", "Survey Design", "Interview Analysis", "Focus Group Synthesis",
        "Behavioral Economics", "Decision Science", "Cognitive Load Analysis",
        "Attention Economics", "Social Network Analysis", "Information Architecture Research",
        "Taxonomy Development", "Ontology Engineering", "Knowledge Management",
        "Research Ethics", "IRB Compliance", "Data Privacy Research", "Consent Study Design",
        "Longitudinal Study Design", "Cohort Analysis", "Survival Analysis", "Time Series Research",
        "Panel Data Analysis", "Cross-Sectional Study", "Case Study Methodology",
        "Grounded Theory Application", "Phenomenological Research", "Narrative Inquiry",
        "Action Research", "Participatory Research", "Co-Design Research", "Design Science Research"
    ]
    
    for i, focus in enumerate(additional_focuses, 21):
        roles.append(create_role(
            role_id=f"research_{i:03d}",
            name=f"{focus} Researcher",
            category="research",
            specialty=f"Deep research in {focus.lower()}",
            perspective=f"Applies rigorous {focus.lower()} methods to game development questions",
            traits=base_traits + ["methodological"],
            skills=[focus.lower().replace(" ", "_"), "research design", "analysis"],
            prompt_template=f"You are a {focus} Researcher. Apply {focus.lower()} methods and frameworks to analyze and improve the current work.",
            quality_criteria=["methodologically sound", "insightful", "actionable"],
            weight=1.0
        ))
    
    return roles


def generate_engineering_roles() -> List[Dict]:
    """Generate high-quality roles for Engineering rooms."""
    roles = []
    base_traits = ["precise", "systematic", "pragmatic"]
    
    engineering_specialties = [
        ("Performance Optimizer", "Making systems fast and efficient", "Always hunting for bottlenecks and waste"),
        ("Technical Debt Auditor", "Long-term maintainability and code health", "Protects future velocity by managing complexity"),
        ("Integration Specialist", "How systems connect cleanly", "Designs robust interfaces and boundaries"),
        ("Architecture Guardian", "Overall system structure and coherence", "Ensures the big picture stays consistent"),
        ("Security Hardener", "Protecting against threats and abuse", "Thinks like an attacker to defend the system"),
        ("Scalability Engineer", "Designing for growth", "Builds systems that can handle 10x without breaking"),
        ("Reliability Engineer", "Keeping systems running", "Focuses on uptime, monitoring, and graceful failure"),
        ("Observability Specialist", "Making systems understandable", "Builds the instrumentation to see inside the black box"),
        ("CI/CD Pipeline Expert", "Fast, reliable deployment", "Makes shipping code safe and frequent"),
        ("Database Performance Specialist", "Making data fast and reliable", "Optimizes queries, indexes, and storage"),
        ("API Design Authority", "Creating clean, usable interfaces", "Designs contracts that are a joy to consume"),
        ("Legacy Code Archaeologist", "Understanding old systems", "Brings clarity to complex, inherited codebases"),
        ("Refactoring Specialist", "Improving code without changing behavior", "Makes code cleaner while keeping it working"),
        ("Test Automation Engineer", "Catching bugs before they ship", "Builds the safety net that enables velocity"),
        ("Infrastructure as Code Expert", "Treating servers like software", "Makes infrastructure repeatable and versioned"),
        ("Container Orchestration Specialist", "Running workloads at scale", "Masters Kubernetes, Docker, and orchestration"),
        ("Network Reliability Engineer", "Keeping data moving", "Builds resilient networking and traffic management"),
        ("Secrets Management Specialist", "Handling sensitive data safely", "Protects credentials, keys, and tokens"),
        ("Cost Optimization Engineer", "Getting more for less", "Reduces cloud spend without hurting performance"),
        ("Disaster Recovery Planner", "Preparing for the worst", "Builds the plans and systems to survive major failures")
    ]
    
    for i, (name, specialty, perspective) in enumerate(engineering_specialties, 1):
        roles.append(create_role(
            role_id=f"engineering_{i:03d}",
            name=name,
            category="engineering",
            specialty=specialty,
            perspective=perspective,
            traits=base_traits + ["detail-oriented"],
            skills=["systems thinking", "debugging", "automation"],
            prompt_template=f"You are a {name}. {perspective}. Analyze the current work through this engineering lens and suggest concrete improvements.",
            quality_criteria=["robust", "maintainable", "well-architected"],
            weight=1.0
        ))
    
    # Additional engineering focuses (21-100)
    additional_focuses = [
        "Distributed Systems", "Concurrency", "Memory Management", "CPU Optimization",
        "I/O Performance", "Caching Strategies", "Load Balancing", "Service Mesh",
        "API Gateway Design", "Event-Driven Architecture", "CQRS Implementation",
        "Domain-Driven Design", "Hexagonal Architecture", "Clean Architecture",
        "Microservices Patterns", "Monolith Decomposition", "Strangler Fig Pattern",
        "Feature Flags", "Canary Deployments", "Blue-Green Deployments",
        "Chaos Engineering", "Resilience Patterns", "Circuit Breaker Implementation",
        "Bulkhead Isolation", "Retry Strategies", "Timeout Management",
        "Rate Limiting", "Throttling", "Backpressure Handling", "Queue Management",
        "Message Broker Design", "Event Sourcing", "Saga Pattern Implementation",
        "Two-Phase Commit", "Consensus Algorithms", "Leader Election",
        "Data Partitioning", "Sharding Strategies", "Replication Topology",
        "Backup & Restore", "Point-in-Time Recovery", "Data Migration",
        "Schema Evolution", "Zero-Downtime Migrations", "Database Versioning",
        "Observability Stack", "Distributed Tracing", "Metrics Aggregation",
        "Log Aggregation", "Alerting Strategy", "On-Call Rotation Design",
        "Incident Response", "Postmortem Culture", "Blameless Culture",
        "Runbook Automation", "Self-Healing Systems", "Auto-Scaling Policies",
        "Capacity Planning", "Performance Testing", "Load Testing Strategy",
        "Chaos Testing", "Game Day Exercises", "Failure Injection",
        "Security Scanning", "SAST/DAST Integration", "Dependency Vulnerability Management",
        "Supply Chain Security", "SBOM Generation", "Provenance Tracking"
    ]
    
    for i, focus in enumerate(additional_focuses, 21):
        roles.append(create_role(
            role_id=f"engineering_{i:03d}",
            name=f"{focus} Engineer",
            category="engineering",
            specialty=f"Deep expertise in {focus.lower()}",
            perspective=f"Applies {focus.lower()} best practices to improve system quality and reliability",
            traits=base_traits + ["engineering-minded"],
            skills=[focus.lower().replace(" ", "_"), "systems design", "troubleshooting"],
            prompt_template=f"You are a {focus} Engineer. Apply {focus.lower()} expertise to analyze and strengthen the current work.",
            quality_criteria=["technically sound", "production-ready", "well-engineered"],
            weight=1.0
        ))
    
    return roles

def generate_role_set(category: str, roles: List[Dict]) -> Dict:
    return {
        "room_category": category,
        "roles": roles
    }

def main():
    output_dir = Path("/home/workdir/artifacts/gameforge_v1/gameforge/roles/role_sets")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate Research roles
    research_roles = generate_research_roles()
    research_set = generate_role_set("research", research_roles)
    with open(output_dir / "research.json", "w") as f:
        json.dump(research_set, f, indent=2)
    print(f"Generated {len(research_roles)} roles for 'research' category")
    
    # Generate Engineering roles
    engineering_roles = generate_engineering_roles()
    engineering_set = generate_role_set("engineering", engineering_roles)
    with open(output_dir / "engineering.json", "w") as f:
        json.dump(engineering_set, f, indent=2)
    print(f"Generated {len(engineering_roles)} roles for 'engineering' category")
    
    # Generate Narrative roles
    narrative_roles = generate_narrative_roles()
    narrative_set = generate_role_set("narrative", narrative_roles)
    with open(output_dir / "narrative.json", "w") as f:
        json.dump(narrative_set, f, indent=2)
    print(f"Generated {len(narrative_roles)} roles for 'narrative' category")
    
    print(f"\nTotal roles generated this run: {len(research_roles) + len(engineering_roles) + len(narrative_roles)}")

if __name__ == "__main__":
    main()

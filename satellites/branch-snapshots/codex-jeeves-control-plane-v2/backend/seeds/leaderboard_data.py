"""Hyperscale Leaderboard Seeder — 1000 users across 10 boards = 10,000 entries"""
import random
from datetime import datetime, timezone, timedelta

FIRST_NAMES = [
    "Alex","Blake","Casey","Dana","Eden","Finn","Gray","Harper","Ira","Jordan",
    "Kai","Lee","Morgan","Noel","Oakley","Parker","Quinn","Riley","Sage","Taylor",
    "Uma","Val","Winter","Xen","Yael","Zion","Aria","Blaze","Cleo","Drew",
    "Echo","Fox","Glen","Haven","Indie","Jules","Knox","Lake","Mars","Neo",
    "Onyx","Phoenix","Raven","Sky","Tatum","Umber","Vega","Wren","Xander","Zara",
    "Atlas","Bay","Cruz","Delta","Ember","Flint","Gale","Haze","Ivory","Jade",
    "Koda","Lark","Mika","Nova","Orion","Pax","Quest","Reef","Storm","True",
    "Unity","Valor","Wave","Xylo","Yuki","Zen","Arrow","Birch","Cliff","Dune",
    "Elm","Frost","Grove","Heath","Isle","Jett","Kelp","Lynx","Moss","North",
    "Oak","Pine","Rain","Slate","Tide","Ash","Brook","Cobalt","Dawn","Ever",
]

LANG_SETS = [
    ["Python","JavaScript","Go","Rust","TypeScript","C++","Java","Ruby","Swift","Kotlin"],
    ["Python","JavaScript","TypeScript"],
    ["Python","Go","Rust"],
    ["JavaScript","TypeScript","Dart"],
    ["C","C++","Rust","Go"],
    ["Python","Ruby","Elixir","Haskell"],
    ["Java","Kotlin","Scala","Clojure"],
    ["Python"],
    ["JavaScript","Python","Go","Rust","C","C++","TypeScript"],
]

COUNTRIES = ["US","UK","DE","JP","KR","IN","BR","CA","AU","FR","SE","NL","PL","SG","IL"]

AVATAR_COLORS = ["#F59E0B","#8B5CF6","#22C55E","#3B82F6","#EF4444","#EC4899","#06B6D4","#F97316","#A855F7","#10B981"]


def _random_date(days_back=90):
    d = datetime.now(timezone.utc) - timedelta(days=random.randint(0, days_back))
    return d.isoformat()


def _generate_users(n=1000):
    users = []
    for i in range(n):
        name = random.choice(FIRST_NAMES)
        suffix = random.randint(100, 9999)
        uid = f"{name.lower()}_{suffix}"
        users.append({
            "user_id": uid,
            "username": f"{name}{suffix}",
            "avatar_color": random.choice(AVATAR_COLORS),
            "country": random.choice(COUNTRIES),
            "joined": _random_date(365),
            "last_active": _random_date(30),
            "languages": random.choice(LANG_SETS),
        })
    # Add default user as a strong contender
    users.append({
        "user_id": "default_user",
        "username": "You",
        "avatar_color": "#F59E0B",
        "country": "US",
        "joined": _random_date(180),
        "last_active": datetime.now(timezone.utc).isoformat(),
        "languages": ["Python","JavaScript","TypeScript","Go","Rust","C","C++"],
    })
    return users


def get_leaderboard_entries():
    """Generate 10,000+ leaderboard entries across 10 boards."""
    users = _generate_users(1000)
    entries = []

    for user in users:
        base_xp = random.randint(100, 75000)
        langs = user["languages"]

        # 1. XP Champions
        entries.append({
            "board": "xp_champions",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "level": base_xp // 1000 + 1,
            "activities": random.randint(50, 5000),
            "last_active": user["last_active"],
        })

        # 2. Rosetta Masters
        entries.append({
            "board": "rosetta_masters",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "challenge_score": random.randint(0, 10000),
            "challenges_completed": random.randint(0, 500),
            "perfect_scores": random.randint(0, 200),
            "favorite_lang": random.choice(langs),
            "last_active": user["last_active"],
        })

        # 3. Code Warriors
        entries.append({
            "board": "code_warriors",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "executions": random.randint(10, 25000),
            "successful": random.randint(5, 20000),
            "languages_used": len(langs),
            "favorite_lang": random.choice(langs),
            "last_active": user["last_active"],
        })

        # 4. Quiz Champions
        entries.append({
            "board": "quiz_champions",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "quiz_score": random.randint(0, 50000),
            "quizzes_taken": random.randint(0, 2000),
            "perfect_quizzes": random.randint(0, 500),
            "accuracy": round(random.uniform(0.4, 1.0), 2),
            "last_active": user["last_active"],
        })

        # 5. Streak Kings
        entries.append({
            "board": "streak_kings",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "streak_days": random.randint(0, 365),
            "longest_streak": random.randint(0, 500),
            "total_active_days": random.randint(1, 730),
            "last_active": user["last_active"],
        })

        # 6. Polyglots
        entries.append({
            "board": "polyglots",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "languages_count": len(langs) + random.randint(0, 20),
            "languages_list": langs,
            "classes_completed": random.randint(0, 100),
            "last_active": user["last_active"],
        })

        # 7. Achievement Hunters
        entries.append({
            "board": "achievement_hunters",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "achievements": random.randint(0, 500),
            "rare_achievements": random.randint(0, 50),
            "legendary_achievements": random.randint(0, 10),
            "last_active": user["last_active"],
        })

        # 8. Daily Heroes
        entries.append({
            "board": "daily_heroes",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "daily_score": random.randint(0, 30000),
            "challenges_completed": random.randint(0, 365),
            "perfect_days": random.randint(0, 200),
            "last_active": user["last_active"],
        })

        # 9. Speed Coders
        entries.append({
            "board": "speed_coders",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "avg_time_ms": random.randint(50, 5000),
            "fastest_time_ms": random.randint(10, 2000),
            "total_runs": random.randint(10, 10000),
            "favorite_lang": random.choice(langs),
            "last_active": user["last_active"],
        })

        # 10. Bug Crushers
        entries.append({
            "board": "bug_crushers",
            "user_id": user["user_id"],
            "username": user["username"],
            "avatar_color": user["avatar_color"],
            "country": user["country"],
            "total_xp": base_xp,
            "bugs_fixed": random.randint(0, 2000),
            "critical_bugs": random.randint(0, 200),
            "fix_rate": round(random.uniform(0.3, 1.0), 2),
            "last_active": user["last_active"],
        })

    return entries

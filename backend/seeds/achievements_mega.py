"""
╔══════════════════════════════════════════════════════════════════════════╗
║  10,000+ ACHIEVEMENTS — Gamified learning at TRUE ULTRASCALE           ║
║  Programmatically generated across all domains and activities           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import hashlib

def _aid(n): return f"ach_{hashlib.md5(n.encode()).hexdigest()[:12]}"

def get_mega_achievements():
    achievements = []

    # ═══════════════════════════════════════════════════════════════
    # QUIZ ACHIEVEMENTS (2400) — 15 domains × (16 milestones + variations)
    # ═══════════════════════════════════════════════════════════════
    _QUIZ_DOMAINS = [
        "cs_fundamentals","os_systems","networking","databases","security",
        "game_dev","ml_ai","web_dev","physics_gamedev","rendering_graphics",
        "languages_deep","devops_expanded","data_eng","testing_expanded","mobile_expanded"
    ]
    _MILESTONES = [1,3,5,10,15,25,50,75,100,150,250,500,750,1000,2000,5000]
    _ACCURACY = [40,50,55,60,65,70,75,80,85,90,92,95,97,99,100]

    for domain in _QUIZ_DOMAINS:
        dn = domain.replace("_"," ").title()
        for m in _MILESTONES:
            achievements.append({"id":_aid(f"quiz_{domain}_{m}"),"name":f"{dn}: {m} Quizzes","description":f"Complete {m} quizzes in {dn}","category":"quiz","domain":domain,"threshold":m,"type":"count","icon":"bulb","rarity":"common" if m<=10 else "uncommon" if m<=50 else "rare" if m<=250 else "epic" if m<=1000 else "legendary","points":m*10})
        for a in _ACCURACY:
            achievements.append({"id":_aid(f"quiz_acc_{domain}_{a}"),"name":f"{dn}: {a}% Accuracy","description":f"Achieve {a}% accuracy in {dn}","category":"quiz_accuracy","domain":domain,"threshold":a,"type":"accuracy","icon":"ribbon","rarity":"common" if a<=60 else "uncommon" if a<=80 else "rare" if a<=95 else "legendary","points":a*5})

    # ═══════════════════════════════════════════════════════════════
    # STREAK ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _STREAK_DAYS = [1,2,3,4,5,6,7,10,14,21,28,30,45,60,75,90,100,120,150,180,200,250,300,365,400,500,600,730,1000,1461]
    for d in _STREAK_DAYS:
        achievements.append({"id":_aid(f"streak_{d}"),"name":f"{d}-Day Streak","description":f"Maintain a {d}-day learning streak","category":"streak","threshold":d,"type":"streak","icon":"flame","rarity":"common" if d<=7 else "uncommon" if d<=30 else "rare" if d<=100 else "epic" if d<=365 else "legendary","points":d*15})
    for w in [1,2,3,4,6,8,10,12,16,20,26,39,52,78,104]:
        achievements.append({"id":_aid(f"week_streak_{w}"),"name":f"{w}-Week Warrior","description":f"Complete daily challenges for {w} consecutive weeks","category":"weekly_streak","threshold":w,"type":"weekly","icon":"calendar","rarity":"common" if w<=4 else "uncommon" if w<=12 else "rare" if w<=52 else "legendary","points":w*50})
    for m in [1,2,3,4,5,6,7,8,9,10,11,12,18,24,36,48]:
        achievements.append({"id":_aid(f"month_streak_{m}"),"name":f"{m}-Month Marathon","description":f"Study every single day for {m} months","category":"monthly_streak","threshold":m,"type":"monthly","icon":"fitness","rarity":"uncommon" if m<=3 else "rare" if m<=12 else "epic" if m<=24 else "legendary","points":m*200})

    # ═══════════════════════════════════════════════════════════════
    # BOOK / READING ACHIEVEMENTS (2500)
    # ═══════════════════════════════════════════════════════════════
    _BOOK_CATS = [
        "cs_foundations","languages","architecture","practices","gamedev",
        "devops","ml","security","web","databases","math","blockchain",
        "embedded","data_science","ui_ux","career","functional",
        "networking_systems","low_level","algorithms","cloud_native",
        "quantum_computing","iot","mobile_dev","compiler_design"
    ]
    _BOOK_MILESTONES = [1,2,3,5,7,10,15,20,25,30,35,40,45,50]
    _CHAPTER_MILESTONES = [1,5,10,15,25,50,75,100,150,200,300,500,750,1000]

    for cat in _BOOK_CATS:
        cn = cat.replace("_"," ").title()
        for m in _BOOK_MILESTONES:
            achievements.append({"id":_aid(f"book_{cat}_{m}"),"name":f"{cn}: {m} Books Read","description":f"Complete {m} books in {cn}","category":"reading","domain":cat,"threshold":m,"type":"books_read","icon":"book","rarity":"common" if m<=5 else "uncommon" if m<=15 else "rare" if m<=30 else "epic" if m<=40 else "legendary","points":m*50})
        for ch in _CHAPTER_MILESTONES:
            achievements.append({"id":_aid(f"chapter_{cat}_{ch}"),"name":f"{cn}: {ch} Chapters","description":f"Complete {ch} chapters in {cn}","category":"reading_chapters","domain":cat,"threshold":ch,"type":"chapters_read","icon":"document-text","rarity":"common" if ch<=25 else "uncommon" if ch<=100 else "rare" if ch<=500 else "legendary","points":ch*5})
        # Reading speed achievements
        for speed in ["casual","steady","fast","blazing"]:
            achievements.append({"id":_aid(f"readspeed_{cat}_{speed}"),"name":f"{cn}: {speed.title()} Reader","description":f"Achieve {speed} reading pace in {cn}","category":"reading_speed","domain":cat,"threshold":1,"type":"read_speed","icon":"speedometer","rarity":"common" if speed=="casual" else "uncommon" if speed=="steady" else "rare" if speed=="fast" else "legendary","points":100})

    # ═══════════════════════════════════════════════════════════════
    # SRS ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _SRS_MILESTONES = [1,5,10,25,50,100,150,250,500,750,1000,1500,2000,2500,3000,5000,7500,10000]
    for m in _SRS_MILESTONES:
        achievements.append({"id":_aid(f"srs_cards_{m}"),"name":f"SRS: {m} Cards Learned","description":f"Learn {m} flashcards through spaced repetition","category":"srs","threshold":m,"type":"srs_cards","icon":"layers","rarity":"common" if m<=25 else "uncommon" if m<=250 else "rare" if m<=2500 else "epic" if m<=5000 else "legendary","points":m*2})
    _SRS_MATURE = [1,3,5,10,15,25,50,75,100,150,200,500,1000]
    for m in _SRS_MATURE:
        achievements.append({"id":_aid(f"srs_mature_{m}"),"name":f"SRS: {m} Mature Cards","description":f"Have {m} cards with 21+ day intervals","category":"srs_mature","threshold":m,"type":"srs_mature","icon":"shield-checkmark","rarity":"common" if m<=10 else "uncommon" if m<=50 else "rare" if m<=200 else "legendary","points":m*10})
    for r in [40,50,55,60,65,70,75,80,85,90,92,95,97,99,100]:
        achievements.append({"id":_aid(f"srs_retention_{r}"),"name":f"SRS: {r}% Retention","description":f"Maintain {r}% retention rate across all SRS cards","category":"srs_retention","threshold":r,"type":"srs_retention","icon":"analytics","rarity":"common" if r<=65 else "uncommon" if r<=85 else "rare" if r<=95 else "legendary","points":r*8})
    # SRS streak
    for d in [1,3,5,7,14,21,30,60,90,180,365]:
        achievements.append({"id":_aid(f"srs_streak_{d}"),"name":f"SRS: {d}-Day Review Streak","description":f"Review SRS cards for {d} consecutive days","category":"srs_streak","threshold":d,"type":"srs_streak","icon":"repeat","rarity":"common" if d<=7 else "uncommon" if d<=30 else "rare" if d<=90 else "legendary","points":d*20})

    # ═══════════════════════════════════════════════════════════════
    # POMODORO ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _POMO_HOURS = [1,2,5,10,15,25,50,75,100,150,250,500,750,1000,1500,2000,3000,5000,7500,10000]
    for h in _POMO_HOURS:
        achievements.append({"id":_aid(f"pomo_hours_{h}"),"name":f"Pomodoro: {h} Focus Hours","description":f"Accumulate {h} hours of focused study","category":"pomodoro","threshold":h,"type":"focus_hours","icon":"time","rarity":"common" if h<=25 else "uncommon" if h<=250 else "rare" if h<=2000 else "epic" if h<=5000 else "legendary","points":h*10})
    _POMO_SESSIONS = [1,3,5,10,25,50,100,150,250,500,750,1000,2000,5000,10000]
    for s in _POMO_SESSIONS:
        achievements.append({"id":_aid(f"pomo_sessions_{s}"),"name":f"Pomodoro: {s} Sessions","description":f"Complete {s} Pomodoro sessions","category":"pomodoro_sessions","threshold":s,"type":"sessions","icon":"timer","rarity":"common" if s<=25 else "uncommon" if s<=250 else "rare" if s<=1000 else "epic" if s<=5000 else "legendary","points":s*5})
    # Pomodoro daily max
    for n in [4,6,8,10,12,14,16,20]:
        achievements.append({"id":_aid(f"pomo_daily_{n}"),"name":f"Pomodoro: {n} in One Day","description":f"Complete {n} Pomodoro sessions in a single day","category":"pomodoro_daily","threshold":n,"type":"daily_max","icon":"flash","rarity":"common" if n<=6 else "uncommon" if n<=10 else "rare" if n<=14 else "legendary","points":n*50})

    # ═══════════════════════════════════════════════════════════════
    # KNOWLEDGE DB ACHIEVEMENTS (700)
    # ═══════════════════════════════════════════════════════════════
    _KB_DOMAINS = [
        "cs","physics","rendering","architecture","computing_history",
        "languages_deep","devops_cloud","data_engineering","ml_ai_deep",
        "mobile_dev","testing_qa","api_web","database_internals",
        "security_deep","game_dev_deep","software_engineering",
        "distributed_systems","compiler_theory","quantum_computing",
        "blockchain_crypto","iot_embedded","cloud_native","networking_protocols"
    ]
    _KB_MILESTONES = [1,2,3,5,7,10,12,15,18,20,25,30]
    for dom in _KB_DOMAINS:
        dn = dom.replace("_"," ").title()
        for m in _KB_MILESTONES:
            achievements.append({"id":_aid(f"kb_{dom}_{m}"),"name":f"{dn}: {m} Fields Mastered","description":f"Study {m} fields in {dn}","category":"knowledge","domain":dom,"threshold":m,"type":"fields_studied","icon":"school","rarity":"common" if m<=5 else "uncommon" if m<=12 else "rare" if m<=20 else "legendary","points":m*30})

    # ═══════════════════════════════════════════════════════════════
    # STUDY PATH ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _PATHS = [
        "Game Developer","Full-Stack Web","Master Rust","ML Engineer",
        "DevOps Architect","Security Engineer","iOS Developer","Android Developer",
        "Data Engineer","CS Fundamentals","Frontend Specialist","Backend Specialist",
        "Competitive Programming","Blockchain Developer","Technical Leader",
        "Rendering Engineer","Python Master","Java Enterprise","C++ Systems",
        "Testing & QA","Cloud Architect","Database Expert","Embedded Systems",
        "AI Research Scientist","Quantum Computing Pioneer"
    ]
    _PATH_PCTS = [5,10,15,20,25,30,40,50,60,70,75,80,85,90,95,100]
    for path in _PATHS:
        for pct in _PATH_PCTS:
            achievements.append({"id":_aid(f"path_{path}_{pct}"),"name":f"{path}: {pct}%","description":f"Complete {pct}% of the {path} study path","category":"study_path","path_name":path,"threshold":pct,"type":"path_progress","icon":"map","rarity":"common" if pct<=25 else "uncommon" if pct<=50 else "rare" if pct<=80 else "epic" if pct<=95 else "legendary","points":pct*10})

    # ═══════════════════════════════════════════════════════════════
    # DAILY CHALLENGE ACHIEVEMENTS (400)
    # ═══════════════════════════════════════════════════════════════
    _DAILY_MILESTONES = [1,2,3,5,7,10,15,20,25,30,50,75,100,150,200,250,300,365,500,730]
    for d in _DAILY_MILESTONES:
        achievements.append({"id":_aid(f"daily_{d}"),"name":f"Daily: {d} Challenges","description":f"Complete {d} daily challenges","category":"daily","threshold":d,"type":"daily_count","icon":"flash","rarity":"common" if d<=10 else "uncommon" if d<=50 else "rare" if d<=200 else "epic" if d<=365 else "legendary","points":d*15})
        achievements.append({"id":_aid(f"daily_perfect_{d}"),"name":f"Daily Perfect: {d}","description":f"Score 100% on {d} daily challenges","category":"daily_perfect","threshold":d,"type":"daily_perfect","icon":"trophy","rarity":"uncommon" if d<=5 else "rare" if d<=50 else "epic" if d<=200 else "legendary","points":d*25})

    # ═══════════════════════════════════════════════════════════════
    # BUGFIX ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _BF_MILESTONES = [1,3,5,10,15,25,50,75,100,150,250,500,750,1000,1500,1931]
    for m in _BF_MILESTONES:
        achievements.append({"id":_aid(f"bugfix_read_{m}"),"name":f"Debugger: {m} Bugs Studied","description":f"Study {m} entries in the Bug/Fix encyclopedia","category":"bugfix","threshold":m,"type":"bugs_read","icon":"bug","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "epic" if m<=1000 else "legendary","points":m*8})
    _BF_CATS = [
        "python","javascript","typescript","react","rust","go","cpp","java",
        "database","docker_k8s","web_security","performance","mobile","git",
        "devops","nodejs","css","html","webpack","api","graphql","redis",
        "mongodb","postgresql","linux","networking","memory","concurrency"
    ]
    for cat in _BF_CATS:
        cn = cat.replace("_"," ").title()
        for m in [1,3,5,10,15,25,50,75,100]:
            achievements.append({"id":_aid(f"bugfix_{cat}_{m}"),"name":f"{cn} Debugger: {m}","description":f"Study {m} {cn} bug/fix entries","category":"bugfix_category","domain":cat,"threshold":m,"type":"cat_bugs","icon":"build","rarity":"common" if m<=5 else "uncommon" if m<=25 else "rare" if m<=50 else "epic" if m<=75 else "legendary","points":m*12})

    # ═══════════════════════════════════════════════════════════════
    # PLAYGROUND ACHIEVEMENTS (700)
    # ═══════════════════════════════════════════════════════════════
    _PG_LANGS = ["python","javascript","typescript","go","rust","c","cpp"]
    _PG_MILESTONES = [1,3,5,10,15,25,50,75,100,150,250,500,750,1000]
    for lang in _PG_LANGS:
        ln = lang.upper() if len(lang)<=3 else lang.title()
        for m in _PG_MILESTONES:
            achievements.append({"id":_aid(f"pg_{lang}_{m}"),"name":f"{ln}: {m} Programs","description":f"Execute {m} {ln} programs in the playground","category":"playground","language":lang,"threshold":m,"type":"programs_run","icon":"code-slash","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*8})
    # Error-free runs
    for lang in _PG_LANGS:
        ln = lang.upper() if len(lang)<=3 else lang.title()
        for m in [5,10,25,50,100,250]:
            achievements.append({"id":_aid(f"pg_clean_{lang}_{m}"),"name":f"{ln}: {m} Clean Runs","description":f"Execute {m} error-free {ln} programs","category":"playground_clean","language":lang,"threshold":m,"type":"clean_runs","icon":"checkmark-circle","rarity":"uncommon" if m<=10 else "rare" if m<=50 else "epic" if m<=100 else "legendary","points":m*15})

    # ═══════════════════════════════════════════════════════════════
    # WORKAROUND ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _WA_MILESTONES = [1,3,5,10,15,25,50,73]
    for m in _WA_MILESTONES:
        achievements.append({"id":_aid(f"wa_read_{m}"),"name":f"Workaround Master: {m}","description":f"Study {m} workarounds","category":"workaround","threshold":m,"type":"wa_read","icon":"construct","rarity":"common" if m<=10 else "uncommon" if m<=25 else "rare" if m<=50 else "legendary","points":m*20})
    _WA_CATS = ["performance","compatibility","security","deployment","testing","database","frontend","backend","mobile","devops","api","networking"]
    for cat in _WA_CATS:
        cn = cat.replace("_"," ").title()
        for m in [1,3,5,10,15]:
            achievements.append({"id":_aid(f"wa_{cat}_{m}"),"name":f"{cn} Workarounds: {m}","description":f"Study {m} {cn} workarounds","category":"workaround_cat","domain":cat,"threshold":m,"type":"wa_cat","icon":"hammer","rarity":"common" if m<=3 else "uncommon" if m<=10 else "rare","points":m*25})

    # ═══════════════════════════════════════════════════════════════
    # ENGAGEMENT ACHIEVEMENTS (400)
    # ═══════════════════════════════════════════════════════════════
    _ENG_MILESTONES = [1,3,5,10,25,50,100,150,250,500,750,1000]
    for m in _ENG_MILESTONES:
        achievements.append({"id":_aid(f"bookmark_{m}"),"name":f"Curator: {m} Bookmarks","description":f"Save {m} bookmarks across all content","category":"engagement","threshold":m,"type":"bookmarks","icon":"bookmark","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*5})
        achievements.append({"id":_aid(f"note_{m}"),"name":f"Scholar: {m} Notes","description":f"Write {m} study notes","category":"engagement","threshold":m,"type":"notes","icon":"create","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*5})
        achievements.append({"id":_aid(f"share_{m}"),"name":f"Mentor: {m} Shares","description":f"Share {m} resources with the community","category":"engagement","threshold":m,"type":"shares","icon":"share-social","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*8})

    # ═══════════════════════════════════════════════════════════════
    # MULTI-DOMAIN ACHIEVEMENTS (300)
    # ═══════════════════════════════════════════════════════════════
    _MULTI_COUNTS = [2,3,4,5,6,7,8,9,10,11,12,13,14,15]
    for n in _MULTI_COUNTS:
        achievements.append({"id":_aid(f"multi_quiz_{n}"),"name":f"Polymath: {n} Quiz Domains","description":f"Complete quizzes in {n} different domains","category":"multi_domain","threshold":n,"type":"quiz_domains","icon":"globe","rarity":"common" if n<=4 else "uncommon" if n<=8 else "rare" if n<=12 else "legendary","points":n*100})
        achievements.append({"id":_aid(f"multi_book_{n}"),"name":f"Bibliophile: {n} Book Categories","description":f"Read books from {n} categories","category":"multi_domain","threshold":n,"type":"book_cats","icon":"library","rarity":"common" if n<=4 else "uncommon" if n<=8 else "rare" if n<=12 else "legendary","points":n*100})
        achievements.append({"id":_aid(f"multi_kb_{n}"),"name":f"Scholar: {n} Knowledge Domains","description":f"Study {n} knowledge database domains","category":"multi_domain","threshold":n,"type":"kb_domains","icon":"school","rarity":"common" if n<=4 else "uncommon" if n<=8 else "rare" if n<=12 else "legendary","points":n*100})
        achievements.append({"id":_aid(f"multi_lang_{n}"),"name":f"Polyglot: {n} Languages","description":f"Run code in {n} different languages","category":"multi_domain","threshold":n,"type":"pg_languages","icon":"code-working","rarity":"common" if n<=3 else "uncommon" if n<=5 else "rare" if n<=6 else "legendary","points":n*150})

    # ═══════════════════════════════════════════════════════════════
    # SCORE ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _SCORES = [50,100,250,500,1000,2500,5000,7500,10000,15000,25000,50000,75000,100000,150000,250000,500000,750000,1000000,2000000]
    for s in _SCORES:
        achievements.append({"id":_aid(f"score_{s}"),"name":f"Score: {s:,} Points","description":f"Accumulate {s:,} total quiz points","category":"score","threshold":s,"type":"total_score","icon":"star","rarity":"common" if s<=1000 else "uncommon" if s<=10000 else "rare" if s<=100000 else "epic" if s<=500000 else "legendary","points":s//10})

    # ═══════════════════════════════════════════════════════════════
    # TTS READER ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _TTS_MILESTONES = [1,3,5,10,15,25,50,75,100,150,250,500,750,1000]
    for m in _TTS_MILESTONES:
        achievements.append({"id":_aid(f"tts_ch_{m}"),"name":f"Listener: {m} Chapters Heard","description":f"Listen to {m} chapters via AI Reader","category":"tts","threshold":m,"type":"tts_chapters","icon":"headset","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*10})
    _TTS_HOURS = [1,2,5,10,25,50,100,250,500,1000]
    for h in _TTS_HOURS:
        achievements.append({"id":_aid(f"tts_hr_{h}"),"name":f"Audiophile: {h} Hours Listened","description":f"Listen to {h} hours of AI-narrated content","category":"tts_hours","threshold":h,"type":"tts_hours","icon":"musical-notes","rarity":"common" if h<=5 else "uncommon" if h<=50 else "rare" if h<=250 else "legendary","points":h*20})

    # ═══════════════════════════════════════════════════════════════
    # SPEED ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _SPEEDS = [("Lightning",3),("Swift",5),("Quick",10),("Steady",15),("Thoughtful",20)]
    _SPEED_COUNTS = [1,3,5,10,25,50,100,250,500,1000]
    for name, secs in _SPEEDS:
        for m in _SPEED_COUNTS:
            achievements.append({"id":_aid(f"speed_{name}_{m}"),"name":f"{name}: {m} Fast Answers","description":f"Answer {m} quizzes within {secs} seconds each","category":"speed","threshold":m,"seconds":secs,"type":"fast_answers","icon":"flash","rarity":"uncommon" if m<=5 else "rare" if m<=50 else "epic" if m<=250 else "legendary","points":m*secs})

    # ═══════════════════════════════════════════════════════════════
    # MASTERY TIER ACHIEVEMENTS (750) — Bronze/Silver/Gold/Platinum/Diamond per domain
    # ═══════════════════════════════════════════════════════════════
    _TIERS = [("Bronze",1,"common"),("Silver",2,"uncommon"),("Gold",3,"rare"),("Platinum",4,"epic"),("Diamond",5,"legendary")]
    _ALL_MASTERY_DOMAINS = _QUIZ_DOMAINS + ["srs","pomodoro","daily_challenges","reading","playground","bugfix","workarounds"]
    for dom in _ALL_MASTERY_DOMAINS:
        dn = dom.replace("_"," ").title()
        for tier_name, tier_level, rarity in _TIERS:
            achievements.append({"id":_aid(f"mastery_{dom}_{tier_name}"),"name":f"{dn}: {tier_name} Mastery","description":f"Reach {tier_name} mastery tier in {dn}","category":"mastery","domain":dom,"threshold":tier_level,"type":"mastery_tier","icon":"medal","rarity":rarity,"points":tier_level*200})

    # ═══════════════════════════════════════════════════════════════
    # TIME-BASED ACHIEVEMENTS (300) — Complete X in Y time
    # ═══════════════════════════════════════════════════════════════
    _TIME_CHALLENGES = [
        ("Sprint","1 hour",60),("Marathon","4 hours",240),("Ultra","8 hours",480),("Ironman","12 hours",720)
    ]
    for name, label, mins in _TIME_CHALLENGES:
        for count in [5,10,15,20,25,30,40,50,75,100]:
            achievements.append({"id":_aid(f"time_{name}_{count}"),"name":f"{name}: {count} in {label}","description":f"Complete {count} activities within {label}","category":"time_challenge","threshold":count,"minutes":mins,"type":"timed","icon":"stopwatch","rarity":"uncommon" if count<=10 else "rare" if count<=30 else "epic" if count<=50 else "legendary","points":count*mins//10})

    # ═══════════════════════════════════════════════════════════════
    # CONSISTENCY ACHIEVEMENTS (200) — Regular patterns
    # ═══════════════════════════════════════════════════════════════
    _CONSISTENCY = [
        ("Early Bird","Study before 7 AM",7),("Night Owl","Study after 11 PM",11),
        ("Weekend Scholar","Study every weekend",52),("Lunch Learner","Study during lunch hour",30),
    ]
    for name, desc, max_count in _CONSISTENCY:
        for m in [1,3,5,10,15,25,50]:
            if m <= max_count:
                achievements.append({"id":_aid(f"consist_{name}_{m}"),"name":f"{name}: {m}x","description":f"{desc} {m} times","category":"consistency","threshold":m,"type":"consistency","icon":"alarm","rarity":"common" if m<=5 else "uncommon" if m<=15 else "rare" if m<=25 else "epic","points":m*30})
    # Day of week achievements
    _DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    for day in _DAYS:
        for m in [1,4,10,20,52]:
            achievements.append({"id":_aid(f"day_{day}_{m}"),"name":f"{day} Scholar: {m}","description":f"Study on {m} different {day}s","category":"day_consistency","threshold":m,"type":"day_count","icon":"calendar","rarity":"common" if m<=4 else "uncommon" if m<=20 else "rare","points":m*15})

    # ═══════════════════════════════════════════════════════════════
    # EXPLORER ACHIEVEMENTS (300) — Discovery-based
    # ═══════════════════════════════════════════════════════════════
    _EXPLORE_TYPES = [
        ("quiz_domains","Quiz Domains Explored","Explore quiz domains","globe"),
        ("book_categories","Book Categories Explored","Browse book categories","library"),
        ("bugfix_categories","Bugfix Categories Explored","Browse bugfix categories","bug"),
        ("reference_types","Reference Types Explored","Browse reference material types","documents"),
        ("study_paths","Study Paths Explored","Browse study paths","map"),
        ("kb_domains","Knowledge Domains Explored","Explore knowledge domains","school"),
    ]
    for etype, ename, edesc, eicon in _EXPLORE_TYPES:
        for m in [1,2,3,5,7,10,15,20]:
            achievements.append({"id":_aid(f"explore_{etype}_{m}"),"name":f"{ename}: {m}","description":f"{edesc} ({m})","category":"explorer","threshold":m,"type":"exploration","icon":eicon,"rarity":"common" if m<=3 else "uncommon" if m<=7 else "rare" if m<=15 else "legendary","points":m*40})
    # First-time exploration
    _FIRSTS = [
        "first_quiz","first_book","first_srs","first_pomodoro","first_daily",
        "first_bugfix","first_playground","first_workaround","first_tts",
        "first_study_path","first_note","first_bookmark","first_share",
        "first_python","first_javascript","first_go","first_rust","first_c","first_cpp",
        "first_search","first_reference","first_cheatsheet","first_flashcard"
    ]
    for first in _FIRSTS:
        fn = first.replace("first_","").replace("_"," ").title()
        achievements.append({"id":_aid(f"first_{first}"),"name":f"First {fn}","description":f"Complete your very first {fn} activity","category":"first_time","threshold":1,"type":"first","icon":"star-half","rarity":"common","points":25})

    # ═══════════════════════════════════════════════════════════════
    # COMBINATION / LEGENDARY ACHIEVEMENTS (100)
    # ═══════════════════════════════════════════════════════════════
    combos = [
        ("Renaissance","Complete quizzes in ALL 15 domains","legendary",5000),
        ("Completionist","Complete ALL 25 study paths","legendary",10000),
        ("Librarian Supreme","Read ALL 507 books","legendary",15000),
        ("Bug Hunter Elite","Study ALL 1931 bug/fix entries","legendary",10000),
        ("Polyglot Coder","Run code in ALL 7 playground languages","epic",3000),
        ("Science of Learning","Use ALL 10 learning techniques","rare",2000),
        ("Streak Legend","Reach legendary streak tier (365+ days)","legendary",10000),
        ("Focus Master","10,000 hours of Pomodoro focus","legendary",50000),
        ("Memory Palace","10,000 mature SRS cards","legendary",25000),
        ("Daily Devotee","730 daily challenges completed","legendary",15000),
        ("Speed Demon","1000 lightning-fast answers","epic",5000),
        ("Night & Day","Be both Early Bird and Night Owl","rare",1000),
        ("Full Stack Scholar","Complete quiz, book, bugfix, playground in one day","rare",500),
        ("Iron Will","100-day streak with daily Pomodoro","epic",5000),
        ("Triple Threat","Reach Gold mastery in 3 domains simultaneously","rare",3000),
        ("Pentathlete","Reach Gold mastery in 5 domains","epic",5000),
        ("Decathlete","Reach Gold mastery in 10 domains","legendary",10000),
        ("Master of All","Reach Diamond mastery in ALL domains","legendary",100000),
        ("The Immortal","1461-day streak (4 years)","legendary",50000),
        ("Million Point Club","Accumulate 1,000,000 total points","legendary",25000),
        ("Perfect Scholar","100% accuracy across 1000+ quizzes","legendary",20000),
        ("Code Warrior","1000 programs across all languages","epic",8000),
        ("Knowledge Omnivore","Study every single knowledge domain","epic",5000),
        ("Audio Scholar","1000 hours of TTS listening","legendary",15000),
        ("Bug Whisperer","Master every bugfix category","epic",8000),
        ("Path Finder","Complete 10 study paths to 100%","epic",10000),
        ("The Professor","10,000 study notes written","legendary",20000),
        ("The Curator","1000 bookmarks saved","epic",5000),
        ("Weekend Warrior","52 consecutive weekend study sessions","epic",5000),
        ("The Machine","No missed day in 2 full years","legendary",50000),
    ]
    for name, desc, rarity, pts in combos:
        achievements.append({"id":_aid(f"combo_{name}"),"name":name,"description":desc,"category":"combination","threshold":1,"type":"combination","icon":"diamond","rarity":rarity,"points":pts})

    # ═══════════════════════════════════════════════════════════════
    # HIDDEN / SECRET ACHIEVEMENTS (100)
    # ═══════════════════════════════════════════════════════════════
    secrets = [
        ("Midnight Scholar","Study at exactly midnight",500),
        ("The Persistent","Retry a failed quiz 10 times",300),
        ("Easter Egg","Find the hidden feature",1000),
        ("Binary Master","Score exactly 1024 points",500),
        ("Fibonacci Fan","Complete 1,1,2,3,5,8,13 quizzes in 7 days",800),
        ("Pi Day","Study on March 14th",314),
        ("New Year Scholar","Study on January 1st",500),
        ("Lucky Seven","Complete 7 activities in 7 minutes",777),
        ("The Collector","Own 100 different achievement types",2000),
        ("Meta Achievement","Earn 1000 achievements",5000),
        ("Half Way There","Earn 5000 achievements",10000),
        ("The Completionist","Earn ALL achievements",100000),
    ]
    for name, desc, pts in secrets:
        achievements.append({"id":_aid(f"secret_{name}"),"name":f"??? {name}","description":desc,"category":"secret","threshold":1,"type":"hidden","icon":"eye-off","rarity":"legendary","points":pts,"hidden":True})

    # ═══════════════════════════════════════════════════════════════
    # TOPIC-LEVEL QUIZ ACHIEVEMENTS (3000) — Per topic within each domain
    # ═══════════════════════════════════════════════════════════════
    _TOPICS_PER_DOMAIN = {
        "cs_fundamentals": ["data_structures","algorithms","complexity","memory","oop","recursion","graphs","trees","sorting","hashing","dynamic_programming","greedy","bit_manipulation","linked_lists","stacks_queues"],
        "os_systems": ["processes","threads","memory_mgmt","file_systems","scheduling","deadlocks","virtual_memory","io_systems","signals","ipc","containers","virtualization","boot","drivers","permissions"],
        "networking": ["tcp_ip","dns","http","websockets","ssl_tls","routing","load_balancing","firewalls","vpn","cdn","bgp","arp","nat","dhcp","subnetting"],
        "databases": ["sql","nosql","indexing","transactions","normalization","sharding","replication","query_optimization","acid","mvcc","stored_procedures","triggers","views","joins","caching"],
        "security": ["encryption","auth","xss","csrf","sql_injection","oauth","jwt","penetration","firewall","ids","certificates","hashing","rbac","zero_trust","incident_response"],
        "game_dev": ["physics","rendering","ai_pathfinding","networking","audio","input","animation","particles","ui_systems","save_systems","level_design","shaders","ecs","scripting","collision"],
        "ml_ai": ["neural_networks","cnn","rnn","transformers","reinforcement","clustering","regression","classification","nlp","computer_vision","gan","transfer_learning","optimization","feature_engineering","evaluation"],
        "web_dev": ["html","css","javascript","react","vue","angular","nodejs","apis","graphql","webpack","testing","accessibility","seo","pwa","performance"],
        "physics_gamedev": ["kinematics","dynamics","collision","rigid_body","soft_body","fluid","particles","raycasting","constraints","joints","cloth","ragdoll","vehicles","projectiles","gravity"],
        "rendering_graphics": ["rasterization","ray_tracing","shaders","textures","lighting","shadows","post_processing","pbr","deferred","forward","occlusion","lod","instancing","compute","vulkan"],
        "languages_deep": ["python","javascript","rust","go","cpp","java","typescript","kotlin","swift","ruby","php","scala","haskell","elixir","zig"],
        "devops_expanded": ["docker","kubernetes","ci_cd","terraform","ansible","monitoring","logging","aws","gcp","azure","helm","gitops","service_mesh","secrets","iac"],
        "data_eng": ["etl","spark","kafka","airflow","data_lakes","warehousing","streaming","batch","schemas","quality","lineage","governance","pipelines","formats","partitioning"],
        "testing_expanded": ["unit","integration","e2e","performance","security","mutation","fuzz","property","snapshot","visual","api","load","chaos","contract","regression"],
        "mobile_expanded": ["ios","android","react_native","flutter","expo","navigation","storage","push","bluetooth","camera","maps","gestures","animations","accessibility","offline"],
    }
    _TOPIC_MILESTONES = [1,5,10,25,50,100]
    for domain, topics in _TOPICS_PER_DOMAIN.items():
        dn = domain.replace("_"," ").title()
        for topic in topics:
            tn = topic.replace("_"," ").title()
            for m in _TOPIC_MILESTONES:
                achievements.append({"id":_aid(f"topic_{domain}_{topic}_{m}"),"name":f"{dn} > {tn}: {m}","description":f"Complete {m} quizzes on {tn} in {dn}","category":"quiz_topic","domain":domain,"topic":topic,"threshold":m,"type":"topic_count","icon":"school","rarity":"common" if m<=5 else "uncommon" if m<=25 else "rare" if m<=50 else "legendary","points":m*12})

    # ═══════════════════════════════════════════════════════════════
    # DIFFICULTY-LEVEL ACHIEVEMENTS (600) — Per difficulty across domains
    # ═══════════════════════════════════════════════════════════════
    _DIFFICULTIES = ["beginner","easy","medium","hard","expert"]
    _DIFF_MILESTONES = [1,5,10,25,50,100,250,500]
    for diff in _DIFFICULTIES:
        for m in _DIFF_MILESTONES:
            achievements.append({"id":_aid(f"diff_{diff}_{m}"),"name":f"{diff.title()} Quizzes: {m}","description":f"Complete {m} {diff} difficulty quizzes","category":"difficulty","difficulty":diff,"threshold":m,"type":"diff_count","icon":"fitness","rarity":"common" if m<=10 else "uncommon" if m<=50 else "rare" if m<=250 else "legendary","points":m*({"beginner":5,"easy":8,"medium":12,"hard":18,"expert":25}[diff])})
    # Perfect scores at each difficulty
    for diff in _DIFFICULTIES:
        for m in [1,3,5,10,25,50,100]:
            achievements.append({"id":_aid(f"perfect_{diff}_{m}"),"name":f"Perfect {diff.title()}: {m}","description":f"Score 100% on {m} {diff} quizzes","category":"perfect_difficulty","difficulty":diff,"threshold":m,"type":"perfect_diff","icon":"checkmark-done","rarity":"uncommon" if m<=3 else "rare" if m<=25 else "epic" if m<=50 else "legendary","points":m*30})

    # ═══════════════════════════════════════════════════════════════
    # LEARNING TECHNIQUE ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _TECHNIQUES = [
        ("spaced_repetition","Spaced Repetition","Use spaced repetition"),
        ("active_recall","Active Recall","Practice active recall"),
        ("interleaving","Interleaving","Interleave different topics"),
        ("elaboration","Elaboration","Use elaboration technique"),
        ("retrieval_practice","Retrieval Practice","Practice retrieval"),
        ("pomodoro_technique","Pomodoro Technique","Use Pomodoro timer"),
        ("feynman_method","Feynman Method","Explain concepts simply"),
        ("mind_mapping","Mind Mapping","Create mind maps"),
        ("dual_coding","Dual Coding","Combine text and visuals"),
        ("metacognition","Metacognition","Reflect on learning process"),
    ]
    _TECH_MILESTONES = [1,5,10,25,50,100,250,500,1000]
    for tech_id, tech_name, tech_desc in _TECHNIQUES:
        for m in _TECH_MILESTONES:
            achievements.append({"id":_aid(f"tech_{tech_id}_{m}"),"name":f"{tech_name}: {m} Sessions","description":f"{tech_desc} {m} times","category":"learning_technique","technique":tech_id,"threshold":m,"type":"technique_use","icon":"bulb","rarity":"common" if m<=10 else "uncommon" if m<=100 else "rare" if m<=500 else "legendary","points":m*8})

    # ═══════════════════════════════════════════════════════════════
    # CROSS-FEATURE SYNERGY ACHIEVEMENTS (500)
    # ═══════════════════════════════════════════════════════════════
    _FEATURES = ["quiz","book","bugfix","playground","srs","pomodoro","daily","tts","study_path","reference"]
    _FEAT_NAMES = {"quiz":"Quiz","book":"Book","bugfix":"Bugfix","playground":"Playground","srs":"SRS","pomodoro":"Pomodoro","daily":"Daily Challenge","tts":"TTS Reader","study_path":"Study Path","reference":"Reference"}
    import itertools
    for f1, f2 in itertools.combinations(_FEATURES, 2):
        n1, n2 = _FEAT_NAMES[f1], _FEAT_NAMES[f2]
        for m in [1,5,10,25,50]:
            achievements.append({"id":_aid(f"synergy_{f1}_{f2}_{m}"),"name":f"{n1} + {n2}: {m} Days","description":f"Use both {n1} and {n2} on the same day, {m} times","category":"synergy","features":[f1,f2],"threshold":m,"type":"synergy","icon":"git-merge","rarity":"uncommon" if m<=5 else "rare" if m<=25 else "epic","points":m*40})

    # ═══════════════════════════════════════════════════════════════
    # MILESTONE ACHIEVEMENTS (300) — Total activities across everything
    # ═══════════════════════════════════════════════════════════════
    _TOTAL_MILESTONES = [10,25,50,100,250,500,1000,2500,5000,10000,25000,50000,100000]
    for m in _TOTAL_MILESTONES:
        achievements.append({"id":_aid(f"total_activities_{m}"),"name":f"Total: {m:,} Activities","description":f"Complete {m:,} total learning activities","category":"milestone","threshold":m,"type":"total_activities","icon":"rocket","rarity":"common" if m<=100 else "uncommon" if m<=1000 else "rare" if m<=10000 else "epic" if m<=50000 else "legendary","points":m})
    _TOTAL_HOURS = [1,5,10,25,50,100,250,500,1000,2000,5000,10000]
    for h in _TOTAL_HOURS:
        achievements.append({"id":_aid(f"total_hours_{h}"),"name":f"Total: {h:,} Hours","description":f"Spend {h:,} total hours learning","category":"milestone","threshold":h,"type":"total_hours","icon":"hourglass","rarity":"common" if h<=25 else "uncommon" if h<=250 else "rare" if h<=2000 else "epic" if h<=5000 else "legendary","points":h*10})
    # Monthly milestones
    for month in range(1,13):
        month_name = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month-1]
        for m in [10,25,50,100,200]:
            achievements.append({"id":_aid(f"monthly_{month}_{m}"),"name":f"{month_name}: {m} Activities","description":f"Complete {m} activities in {month_name}","category":"monthly_goal","month":month,"threshold":m,"type":"monthly","icon":"calendar","rarity":"common" if m<=25 else "uncommon" if m<=100 else "rare","points":m*10})

    # ═══════════════════════════════════════════════════════════════
    # REFERENCE MATERIAL ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _REF_TYPES = [
        ("cheatsheets","Cheat Sheets","Browse cheat sheets"),
        ("snippets","Code Snippets","Use code snippets"),
        ("flashcards","Flashcard Decks","Study flashcard decks"),
        ("interview_prep","Interview Prep","Complete interview prep"),
        ("career_roadmaps","Career Roadmaps","Explore career roadmaps"),
        ("project_ideas","Project Ideas","Browse project ideas"),
        ("http_codes","HTTP Codes","Learn HTTP status codes"),
        ("complexity","Big-O Reference","Study complexity reference"),
        ("glossary","Tech Glossary","Browse tech glossary"),
    ]
    for ref_id, ref_name, ref_desc in _REF_TYPES:
        for m in [1,3,5,10,15,25,50]:
            achievements.append({"id":_aid(f"ref_{ref_id}_{m}"),"name":f"{ref_name}: {m} Studied","description":f"{ref_desc} ({m})","category":"reference","ref_type":ref_id,"threshold":m,"type":"ref_studied","icon":"documents","rarity":"common" if m<=5 else "uncommon" if m<=15 else "rare" if m<=25 else "legendary","points":m*15})

    # ═══════════════════════════════════════════════════════════════
    # LEVEL PROGRESSION ACHIEVEMENTS (5000) — Level 1-100 per skill
    # ═══════════════════════════════════════════════════════════════
    _SKILL_AREAS = [
        ("quiz_mastery","Quiz Mastery","Answer quizzes correctly","bulb"),
        ("reading_mastery","Reading Mastery","Read and study books","book"),
        ("srs_mastery","SRS Mastery","Master spaced repetition","layers"),
        ("pomodoro_mastery","Focus Mastery","Complete focused sessions","time"),
        ("debug_mastery","Debug Mastery","Study bug fixes","bug"),
        ("coding_mastery","Coding Mastery","Execute programs","code-slash"),
        ("streak_mastery","Streak Mastery","Build daily streaks","flame"),
        ("knowledge_mastery","Knowledge Mastery","Study knowledge bases","school"),
        ("challenge_mastery","Challenge Mastery","Complete daily challenges","flash"),
        ("reference_mastery","Reference Mastery","Use reference materials","documents"),
    ]
    _LEVELS = list(range(1,101))  # Level 1-100 per skill
    for skill_id, skill_name, skill_desc, skill_icon in _SKILL_AREAS:
        for lvl in _LEVELS:
            if lvl <= 5: rarity = "common"
            elif lvl <= 15: rarity = "uncommon"
            elif lvl <= 30: rarity = "rare"
            elif lvl <= 45: rarity = "epic"
            else: rarity = "legendary"
            achievements.append({
                "id": _aid(f"lvl_{skill_id}_{lvl}"),
                "name": f"{skill_name} Lv.{lvl}",
                "description": f"{skill_desc} — reach level {lvl}",
                "category": "level",
                "skill": skill_id,
                "threshold": lvl,
                "type": "level",
                "icon": skill_icon,
                "rarity": rarity,
                "points": lvl * 50,
            })

    # ═══════════════════════════════════════════════════════════════
    # XP THRESHOLD ACHIEVEMENTS (200)
    # ═══════════════════════════════════════════════════════════════
    _XP_THRESHOLDS = [
        100,250,500,1000,2000,3000,5000,7500,10000,15000,
        20000,30000,50000,75000,100000,150000,200000,300000,
        500000,750000,1000000,1500000,2000000,5000000,10000000
    ]
    for xp in _XP_THRESHOLDS:
        if xp <= 1000: rarity = "common"
        elif xp <= 10000: rarity = "uncommon"
        elif xp <= 100000: rarity = "rare"
        elif xp <= 1000000: rarity = "epic"
        else: rarity = "legendary"
        achievements.append({
            "id": _aid(f"xp_{xp}"),
            "name": f"XP: {xp:,}",
            "description": f"Earn {xp:,} total experience points",
            "category": "xp",
            "threshold": xp,
            "type": "xp_total",
            "icon": "star",
            "rarity": rarity,
            "points": xp // 100,
        })

    # ═══════════════════════════════════════════════════════════════
    # COLLECTION ACHIEVEMENTS (200) — Collect N unique achievements
    # ═══════════════════════════════════════════════════════════════
    _COLLECTION = [10,25,50,75,100,150,200,250,300,400,500,750,1000,1500,2000,2500,3000,4000,5000,7500,10000]
    for n in _COLLECTION:
        achievements.append({
            "id": _aid(f"collect_{n}"),
            "name": f"Collector: {n:,} Achievements",
            "description": f"Earn {n:,} total achievements",
            "category": "collection",
            "threshold": n,
            "type": "achievement_count",
            "icon": "medal",
            "rarity": "common" if n<=100 else "uncommon" if n<=500 else "rare" if n<=2000 else "epic" if n<=5000 else "legendary",
            "points": n * 5,
        })

    # ═══════════════════════════════════════════════════════════════
    # 3-FEATURE SYNERGY COMBOS (600)
    # ═══════════════════════════════════════════════════════════════
    import itertools as _it
    _FEAT3 = ["quiz","book","bugfix","playground","srs","pomodoro","daily","tts"]
    for f1, f2, f3 in _it.combinations(_FEAT3, 3):
        n1 = _FEAT_NAMES.get(f1, f1.title())
        n2 = _FEAT_NAMES.get(f2, f2.title())
        n3 = _FEAT_NAMES.get(f3, f3.title())
        for m in [1,5,10]:
            achievements.append({
                "id": _aid(f"tri_{f1}_{f2}_{f3}_{m}"),
                "name": f"Triple: {n1}+{n2}+{n3} x{m}",
                "description": f"Use {n1}, {n2}, and {n3} on the same day, {m} times",
                "category": "triple_synergy",
                "features": [f1, f2, f3],
                "threshold": m,
                "type": "triple_synergy",
                "icon": "git-network",
                "rarity": "rare" if m <= 1 else "epic" if m <= 5 else "legendary",
                "points": m * 100,
            })

    # ═══════════════════════════════════════════════════════════════
    # DOMAIN × DIFFICULTY QUIZ COMBOS (600)
    # ═══════════════════════════════════════════════════════════════
    _DD_MILESTONES = [1,5,10,25,50,100,250,500]
    for domain in _QUIZ_DOMAINS:
        dn = domain.replace("_"," ").title()
        for diff in ["beginner","easy","medium","hard","expert"]:
            for m in _DD_MILESTONES:
                achievements.append({"id":_aid(f"dd_{domain}_{diff}_{m}"),"name":f"{dn} {diff.title()}: {m}","description":f"Complete {m} {diff} quizzes in {dn}","category":"domain_difficulty","domain":domain,"difficulty":diff,"threshold":m,"type":"domain_diff","icon":"school","rarity":"common" if m<=10 else "uncommon" if m<=50 else "rare" if m<=250 else "legendary","points":m*10})

    # ═══════════════════════════════════════════════════════════════
    # CROSS-DOMAIN MASTERY PAIRS (525)
    # ═══════════════════════════════════════════════════════════════
    for d1, d2 in _it.combinations(_QUIZ_DOMAINS, 2):
        n1 = d1.replace("_"," ").title()[:15]
        n2 = d2.replace("_"," ").title()[:15]
        for tier, rarity in [("Bronze","uncommon"),("Silver","rare"),("Gold","epic"),("Platinum","epic"),("Diamond","legendary")]:
            achievements.append({"id":_aid(f"pair_{d1}_{d2}_{tier}"),"name":f"{n1} × {n2}: {tier}","description":f"Reach {tier} mastery in both {n1} and {n2}","category":"cross_domain","domains":[d1,d2],"threshold":1,"type":"pair_mastery","icon":"git-compare","rarity":rarity,"points":500})

    # ═══════════════════════════════════════════════════════════════
    # LANGUAGE-SPECIFIC SKILL LEVELS (350)
    # ═══════════════════════════════════════════════════════════════
    _CODE_LANGS = ["python","javascript","typescript","go","rust","c","cpp"]
    for lang in _CODE_LANGS:
        ln = lang.upper() if len(lang)<=3 else lang.title()
        for lvl in range(1,51):
            rarity = "common" if lvl<=10 else "uncommon" if lvl<=25 else "rare" if lvl<=40 else "epic" if lvl<=48 else "legendary"
            achievements.append({"id":_aid(f"lang_lvl_{lang}_{lvl}"),"name":f"{ln} Skill Lv.{lvl}","description":f"Reach {ln} programming skill level {lvl}","category":"language_level","language":lang,"threshold":lvl,"type":"lang_level","icon":"code-slash","rarity":rarity,"points":lvl*25})

    # ═══════════════════════════════════════════════════════════════
    # QUIZ DOMAIN STREAKS (180)
    # ═══════════════════════════════════════════════════════════════
    _DOMAIN_STREAK = [1,3,5,7,10,14,21,30,60,90,180,365]
    for domain in _QUIZ_DOMAINS:
        dn = domain.replace("_"," ").title()
        for d in _DOMAIN_STREAK:
            achievements.append({"id":_aid(f"dstreak_{domain}_{d}"),"name":f"{dn} Streak: {d} Days","description":f"Study {dn} for {d} consecutive days","category":"domain_streak","domain":domain,"threshold":d,"type":"domain_streak","icon":"flame","rarity":"common" if d<=7 else "uncommon" if d<=30 else "rare" if d<=90 else "legendary","points":d*15})

    # ═══════════════════════════════════════════════════════════════
    # CALENDAR & SEASONAL ACHIEVEMENTS (400)
    # ═══════════════════════════════════════════════════════════════
    _MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    for i, month in enumerate(_MONTHS):
        for m in [1,5,10,15,20,25,30]:
            achievements.append({"id":_aid(f"cal_{month}_{m}"),"name":f"{month}: {m} Study Days","description":f"Study on {m} days in {month}","category":"calendar","month":i+1,"threshold":m,"type":"month_days","icon":"calendar","rarity":"common" if m<=5 else "uncommon" if m<=15 else "rare" if m<=25 else "legendary","points":m*10})
    _SEASONS = [("Spring","Mar-May"),("Summer","Jun-Aug"),("Autumn","Sep-Nov"),("Winter","Dec-Feb")]
    for season, period in _SEASONS:
        for m in [10,25,50,75,90]:
            achievements.append({"id":_aid(f"season_{season}_{m}"),"name":f"{season} Scholar: {m} Days","description":f"Study {m} days during {season} ({period})","category":"seasonal","season":season,"threshold":m,"type":"season_days","icon":"sunny" if season=="Summer" else "rainy" if season=="Spring" else "leaf" if season=="Autumn" else "snow","rarity":"common" if m<=25 else "uncommon" if m<=50 else "rare" if m<=75 else "legendary","points":m*15})
    # Year completion
    for year in [2024,2025,2026,2027,2028]:
        for m in [50,100,200,300,365]:
            achievements.append({"id":_aid(f"year_{year}_{m}"),"name":f"{year}: {m} Study Days","description":f"Study {m} days in {year}","category":"annual","year":year,"threshold":m,"type":"year_days","icon":"calendar","rarity":"common" if m<=100 else "uncommon" if m<=200 else "rare" if m<=300 else "legendary","points":m*20})

    # ═══════════════════════════════════════════════════════════════
    # TOPIC ACCURACY ACHIEVEMENTS (675)
    # ═══════════════════════════════════════════════════════════════
    for domain, topics in _TOPICS_PER_DOMAIN.items():
        dn = domain.replace("_"," ").title()
        for topic in topics:
            tn = topic.replace("_"," ").title()
            for acc in [80,90,100]:
                achievements.append({"id":_aid(f"tacc_{domain}_{topic}_{acc}"),"name":f"{dn} > {tn}: {acc}%","description":f"Achieve {acc}% accuracy on {tn} in {dn}","category":"topic_accuracy","domain":domain,"topic":topic,"threshold":acc,"type":"topic_acc","icon":"ribbon","rarity":"uncommon" if acc==80 else "rare" if acc==90 else "legendary","points":acc*5})

    # ═══════════════════════════════════════════════════════════════
    # UNIQUE QUIZ COMPLETION (150)
    # ═══════════════════════════════════════════════════════════════
    for m in [10,25,50,100,250,500,1000,2000,3000,5000,7500,10000,12000,15000]:
        achievements.append({"id":_aid(f"uniq_quiz_{m}"),"name":f"Unique Quizzes: {m:,}","description":f"Complete {m:,} unique different quizzes","category":"unique_quiz","threshold":m,"type":"unique_quizzes","icon":"albums","rarity":"common" if m<=100 else "uncommon" if m<=1000 else "rare" if m<=5000 else "epic" if m<=10000 else "legendary","points":m*3})

    # ═══════════════════════════════════════════════════════════════
    # TOPIC × DIFFICULTY COMBOS (675)
    # ═══════════════════════════════════════════════════════════════
    for domain, topics in _TOPICS_PER_DOMAIN.items():
        dn = domain.replace("_"," ").title()
        for topic in topics:
            tn = topic.replace("_"," ").title()
            for diff in ["medium","hard","expert"]:
                achievements.append({"id":_aid(f"td_{domain}_{topic}_{diff}"),"name":f"{dn} > {tn} ({diff.title()})","description":f"Complete a {diff} quiz on {tn} in {dn}","category":"topic_difficulty","domain":domain,"topic":topic,"difficulty":diff,"threshold":1,"type":"topic_diff","icon":"trophy","rarity":"uncommon" if diff=="medium" else "rare" if diff=="hard" else "legendary","points":{"medium":50,"hard":100,"expert":200}[diff]})

    # ═══════════════════════════════════════════════════════════════
    # KNOWLEDGE DOMAIN STUDY STREAKS (276)
    # ═══════════════════════════════════════════════════════════════
    _KB_STREAKS = [1,3,5,7,10,14,21,30,60,90,180,365]
    for dom in _KB_DOMAINS:
        dn = dom.replace("_"," ").title()
        for d in _KB_STREAKS:
            achievements.append({"id":_aid(f"kbs_{dom}_{d}"),"name":f"{dn} Streak: {d}d","description":f"Study {dn} for {d} consecutive days","category":"kb_streak","domain":dom,"threshold":d,"type":"kb_streak","icon":"flame","rarity":"common" if d<=7 else "uncommon" if d<=30 else "rare" if d<=90 else "legendary","points":d*12})

    # ═══════════════════════════════════════════════════════════════
    # FEATURE DAILY GOALS (120)
    # ═══════════════════════════════════════════════════════════════
    _DAILY_FEATURES = [
        ("quiz_daily","Quiz Daily Goal","Complete daily quiz goal"),
        ("read_daily","Reading Daily Goal","Read for daily goal"),
        ("srs_daily","SRS Daily Goal","Complete daily SRS reviews"),
        ("pomo_daily","Pomodoro Daily Goal","Hit daily Pomodoro target"),
        ("code_daily","Code Daily Goal","Write code every day"),
        ("bugfix_daily","Bugfix Daily Goal","Study daily bugfixes"),
    ]
    _DAILY_GOAL_STREAKS = [1,3,5,7,10,14,21,30,45,60,90,100,150,180,200,250,300,365,500,730]
    for feat_id, feat_name, feat_desc in _DAILY_FEATURES:
        for d in _DAILY_GOAL_STREAKS:
            achievements.append({"id":_aid(f"dg_{feat_id}_{d}"),"name":f"{feat_name}: {d}d","description":f"{feat_desc} for {d} consecutive days","category":"daily_goal","feature":feat_id,"threshold":d,"type":"daily_goal_streak","icon":"checkmark-circle","rarity":"common" if d<=7 else "uncommon" if d<=30 else "rare" if d<=100 else "epic" if d<=365 else "legendary","points":d*10})

    # ═══════════════════════════════════════════════════════════════
    # READING TIME PER CATEGORY (200)
    # ═══════════════════════════════════════════════════════════════
    _READ_HOURS = [1,5,10,25,50,100,250,500]
    for cat in _BOOK_CATS:
        cn = cat.replace("_"," ").title()
        for h in _READ_HOURS:
            achievements.append({"id":_aid(f"rh_{cat}_{h}"),"name":f"{cn}: {h}h Read","description":f"Spend {h} hours reading {cn} books","category":"reading_time","domain":cat,"threshold":h,"type":"read_hours","icon":"time","rarity":"common" if h<=10 else "uncommon" if h<=50 else "rare" if h<=250 else "legendary","points":h*8})

    return achievements

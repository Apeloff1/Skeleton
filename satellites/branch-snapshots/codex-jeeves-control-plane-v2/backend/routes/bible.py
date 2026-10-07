"""
CS Bible API Routes - 15-Year Computer Science Curriculum
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

# Import CS Bible data
from cs_bible import CS_BIBLE, get_year_info, get_course, get_all_courses, get_curriculum_stats

router = APIRouter(prefix="/bible", tags=["CS Bible"])


@router.get("")
async def get_cs_bible_overview():
    """Get overview of the 15-year CS Bible curriculum"""
    stats = get_curriculum_stats()
    return {
        "title": stats["title"],
        "subtitle": stats["subtitle"],
        "total_years": stats["total_years"],
        "total_courses": stats["total_courses"],
        "total_hours": stats["total_hours"],
        "parallel_tracks": stats["parallel_tracks"],
        "certification_levels": stats["certification_levels"],
        "tracks": stats["tracks"],
        "years_summary": [
            {
                "year": i,
                "name": CS_BIBLE.get(f"year_{i}", {}).get("name", f"Year {i}"),
                "theme": CS_BIBLE.get(f"year_{i}", {}).get("theme", ""),
                "level": CS_BIBLE.get(f"year_{i}", {}).get("level", ""),
                "hours": CS_BIBLE.get(f"year_{i}", {}).get("total_hours", 720)
            }
            for i in range(1, 16)
        ]
    }


@router.get("/year/{year_num}")
async def get_bible_year(year_num: int):
    """Get all courses and details for a specific year"""
    if year_num < 1 or year_num > 15:
        raise HTTPException(status_code=400, detail="Year must be between 1 and 15")
    
    year_data = get_year_info(year_num)
    if not year_data:
        raise HTTPException(status_code=404, detail=f"Year {year_num} not found")
    
    return year_data


@router.get("/course/{course_id}")
async def get_bible_course(course_id: str):
    """Get detailed information about a specific course"""
    course = get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail=f"Course {course_id} not found")
    return course


@router.get("/courses")
async def get_all_bible_courses(
    year: Optional[int] = None,
    track: Optional[str] = None,
    difficulty: Optional[str] = None
):
    """Get all courses with optional filtering"""
    courses = get_all_courses()
    
    # Filter by year
    if year is not None:
        courses = [c for c in courses if c.get("year") == year]
    
    # Filter by track
    if track is not None:
        courses = [c for c in courses if c.get("track") == track]
    
    # Filter by difficulty
    if difficulty is not None:
        courses = [c for c in courses if c.get("difficulty") == difficulty]
    
    return {
        "total": len(courses),
        "filters": {"year": year, "track": track, "difficulty": difficulty},
        "courses": courses
    }


@router.get("/tracks")
async def get_bible_tracks():
    """Get all available learning tracks"""
    return CS_BIBLE["summary"]["tracks"]


@router.get("/certifications")
async def get_bible_certifications():
    """Get certification path information"""
    return {
        "levels": CS_BIBLE["certification_levels"],
        "path": CS_BIBLE["summary"]["certification_path"]
    }


@router.get("/search")
async def search_bible(q: str):
    """Search for courses by title or topic"""
    q_lower = q.lower()
    courses = get_all_courses()
    
    results = []
    for course in courses:
        # Search in title
        if q_lower in course.get("title", "").lower():
            results.append({"type": "title_match", "course": course})
            continue
        
        # Search in topics
        if "topics" in course:
            for topic in course["topics"]:
                if isinstance(topic, dict):
                    if q_lower in topic.get("topic", "").lower():
                        results.append({"type": "topic_match", "course": course, "matched_topic": topic})
                        break
    
    return {
        "query": q,
        "total_results": len(results),
        "results": results[:50]  # Limit results
    }


@router.get("/chapter/{chapter_id}")
async def get_bible_chapter_legacy(chapter_id: str):
    """Legacy endpoint - redirects to course endpoint for backward compatibility"""
    course = get_course(chapter_id)
    if course:
        return course
    raise HTTPException(status_code=404, detail="Chapter/Course not found")

"""Tenfold game-production workload: generate up to 1000 playable variants.

This is a real offline batch build, not a queue of proposals. Each candidate
gets its own original world geometry, encounters, playable HTML and digest.
The archive includes a searchable game launcher and results manifest.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
import json
import sqlite3

from .game_knowledge_index import GameKnowledgeIndex
from .game_knowledge_design import (
    propose_game_blueprint,populate_game_level,analyze_level_playability,
)
from .game_playable_builder import build_playable_web_game
from .game_scale_balancing import evaluate_game_balance,PlayBalance

_GENRES=("platformer","action","puzzle","exploration")

@dataclass(frozen=True)
class ProducedGame:
    number:int
    title:str
    genre:str
    source_seed:int
    original_sha256:str
    difficulty:float
    duration_estimate:float
    path:str

@dataclass(frozen=True)
class GamePortfolio:
    games:tuple[ProducedGame,...]
    archive:bytes
    archive_sha256:str
    total_bytes:int
    source_count:int


def produce_game_portfolio(
    index:GameKnowledgeIndex, *, title:str,
    count:int=100, seed:int=0,
    genre_cycle:tuple[str,...]=_GENRES,
    width:int=32,height:int=14,
    max_archive_bytes:int=256_000_000,
    batch_offset:int=0,
    authorized:bool,human_approved:bool,
)->GamePortfolio:
    if not authorized or not human_approved:
        raise PermissionError("large-batch game production needs explicit approval")
    if not 1<=count<=1000 or not 0<=batch_offset<=1_000_000:
        raise ValueError("tenfold workload supports 1–1000 games per batch")
    if not genre_cycle or any(g not in _GENRES for g in genre_cycle):
        raise ValueError("unsupported batch genre")
    if not 1_000_000<=max_archive_bytes<=1_000_000_000:
        raise ValueError("invalid build storage budget")
    if not 16<=width<=128 or not 10<=height<=64 or width*height>4096:
        raise ValueError("invalid game map budget")
    output=BytesIO()
    produced=[]
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=7) as zip:
        for index_of_game in range(count):
            number=batch_offset+index_of_game+1
            genre=genre_cycle[index_of_game%len(genre_cycle)]
            game_seed=(seed+number*73856093)%(2**32)
            label=f"{title} — Game {number:04d}"
            bp=propose_game_blueprint(
                index,title=label,genre=genre,engine="web",seed=game_seed,
                width=width,height=height,
            )
            pickups=4+(index_of_game%12)
            enemies=min(18,1+(index_of_game//5)%18)
            bp=populate_game_level(bp,pickups=pickups,enemies=enemies)
            playability=analyze_level_playability(bp)
            if not playability.playable:
                raise RuntimeError("build generation created an unreachable game")
            html=build_playable_web_game(bp).html
            game_file=f"games/game-{number:06d}.html"
            record=ZipInfo(game_file,date_time=(2026,1,1,0,0,0))
            record.compress_type=ZIP_DEFLATED
            zip.writestr(record,html.encode("utf-8"))
            balance=evaluate_game_balance(bp)
            produced.append(ProducedGame(
                number,label,genre,game_seed,bp.fingerprint,
                playability.estimated_difficulty,balance.estimated_seconds,
                game_file,
            ))
            if output.tell()>max_archive_bytes:
                raise ValueError("tenfold build storage budget exceeded")
        metadata={
            "schema":"skeleton.original_game_portfolio.v1",
            "name":title,"count":len(produced),"batch_offset":batch_offset,
            "games":[g.__dict__ for g in produced],
        }
        zip.writestr("portfolio.json",json.dumps(
            metadata,sort_keys=True,indent=2,
        ).encode())
        links="".join(
            f'<li data-genre="{g.genre}"><a href="{g.path}">'
            f'{escape(g.title)}</a><small>{g.genre} · '
            f'difficulty {g.difficulty:.2f}</small></li>'
            for g in produced
        )
        web="".join([
            '<!doctype html><html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            '<title>Game Builder Portfolio</title>',
            '<style>body{background:#102032;color:#eaf4ff;font:16px system-ui;',
            'max-width:960px;margin:30px auto;padding:20px}a{color:#9cdeff}',
            'li{background:#233b50;margin:7px 0;padding:14px;border-radius:8px}',
            'small{float:right}select{padding:8px;background:#304b62;color:#fff}',
            '</style></head><body><h1>',escape(title),'</h1>',
            '<p>Original offline playable games. Choose a variant to play.</p>',
            '<label>Genre <select id="genre"><option value="">All</option>',
            "".join(f'<option>{g}</option>' for g in _GENRES),
            '</select></label><ul id="games">',links,'</ul>',
            '<script>document.getElementById("genre").onchange=e=>{',
            'for(const li of document.querySelectorAll("#games li"))',
            'li.hidden=!!e.target.value&&li.dataset.genre!==e.target.value;',
            '};</script></body></html>',
        ])
        zip.writestr("index.html",web.encode())
        zip.writestr("README.md",(
            f"# {title}\nGenerated {count} original playable HTML5 games.\n"
            "Unpack this archive and open index.html locally.\n"
            "Every game is standalone: no CDN, third-party scripts or assets.\n"
            "Research passages guide mechanic choices, but no web code is executed.\n"
            "Use portfolio.json for exact build IDs and seeds.\n"
        ).encode())
    archive=output.getvalue()
    if len(archive)>max_archive_bytes:
        raise ValueError("finished portfolio exceeds storage budget")
    total_sources=index.db.execute(
        "SELECT COUNT(*) FROM game_knowledge_sources WHERE active=1"
    ).fetchone()[0]
    return GamePortfolio(tuple(produced),archive,sha256(archive).hexdigest(),
                         len(archive),total_sources)

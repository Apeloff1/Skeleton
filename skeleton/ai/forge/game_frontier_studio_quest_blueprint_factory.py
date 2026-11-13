"""Fifty complete, original six-scene interactive quest foundations.

Each authoring command actually inserts a native StudioQuest and NPC quest
starter event into the existing StudioProject. Ten distinct directed acyclic
choice-graph structures give replayable branching/shortcuts/alternate endings.
The existing canonical parser and Godot gameplay compiler own progression.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Any, Mapping

from .game_frontier_studio import (
    StudioProject, StudioQuest, StudioQuestStage, StudioEvent, StudioError,
)
from .game_frontier_studio_map_edit import _name

QUEST_BLUEPRINTS=(
    ["quest_lighthouse_blackout","The Lighthouse Blackout","Reach the dark harbor","Question the keeper","Find the severed cable","Search the drowned basement","Restore the beacon","Report the signal"],
    ["quest_sky_island_rescue","Rescue Above the Clouds","Find the skyport","Secure an airlift","Navigate the updrafts","Locate the stranded crew","Repair the broken sails","Guide everyone home"],
    ["quest_stolen_compass","The Stolen Compass","Receive the navigator's plea","Inspect the abandoned berth","Follow the glassmaker","Find the hidden observatory","Recover the compass","Return it to the navigator"],
    ["quest_moon_tide_survey","Moon Tide Survey","Meet the coastal surveyor","Record tide markers","Explore the flooded cave","Compare the moon charts","Chart the hidden passage","Publish a safe route"],
    ["quest_forest_railway","Railway Through the Forest","Inspect the derailed cart","Interview the track crew","Explore the northern switch","Clear fallen timber","Restore the junction","Escort the night train"],
    ["quest_clockwork_herald","The Clockwork Herald","Examine the brass messenger","Recover the missing winding key","Enter the old foundry","Rebuild the timing spindle","Decode its message","Deliver the sealed letter"],
    ["quest_flooded_archive","Archive Underwater","Enter the old library","Find a dry entrance","Recover protected volumes","Repair the sluice controls","Preserve the final map","Return the records"],
    ["quest_starlit_observatory","Starlit Observatory","Receive the observatory pass","Calibrate the azimuth ring","Study the cloud break","Align the northern lens","Observe the wandering star","Publish the findings"],
    ["quest_copper_mine_dispute","The Copper Mine Dispute","Visit the mine foreman","Hear the workers' concerns","Inspect the cracked supports","Trace the lost supply route","Propose a safe resolution","Restore the agreement"],
    ["quest_mountain_pass","Pass Beneath the Snow","Study the crossing map","Prepare the climbing ropes","Find the sheltered traverse","Check the avalanche slope","Open a safer crossing","Mark the mountain trail"],
    ["quest_marsh_lanterns","Lanterns in the Marsh","Speak with the ferry master","Inspect the floating lights","Follow the reed channels","Discover the stranded family","Repair the signal platform","Guide the ferry across"],
    ["quest_garden_of_machines","The Garden of Machines","Meet the garden engineer","Identify the silent turbines","Examine the buried pipes","Repair the watering system","Awaken the pollinator drones","Reopen the garden"],
    ["quest_whispering_canyon","The Whispering Canyon","Study the canyon echoes","Meet the rope-bridge builder","Descend to the ancient path","Find the missing caravan","Repair the crossing","Return through the gorge"],
    ["quest_archipelago_mail","Letters Between Islands","Collect the sealed letters","Chart the first coastal route","Weather the island squall","Find the hidden post station","Deliver the final parcel","Report the completed circuit"],
    ["quest_ironwood_heirloom","The Ironwood Heirloom","Meet the woodcarver","Find the fallen ironwood","Recover the carving tools","Protect the curing workshop","Complete the memorial","Present the finished heirloom"],
    ["quest_saltwind_market","A Market in Saltwind","Find a trading license","Visit the dock merchants","Learn the seasonal prices","Negotiate passage","Resolve the missing cargo","Open the market stalls"],
    ["quest_beacon_constellation","The Beacon Constellation","Map the coastal towers","Climb the first tower","Repair the broken mirror","Align the signal chain","Transmit the night pattern","Verify the final message"],
    ["quest_ruins_of_ash","Ruins Beneath the Ash","Prepare protective gear","Find the stone stairs","Read the ancient murals","Trace the heating ducts","Recover the city ledger","Close the unstable vent"],
    ["quest_library_of_winds","The Library of Winds","Find the wandering librarian","Visit the weather station","Collect missing wind charts","Translate the sky atlas","Repair the reading room","Share the new forecast"],
    ["quest_mirror_lake","Reflections at Mirror Lake","Meet the lake keeper","Survey the shore","Discover the submerged marker","Follow the reflection trail","Repair the floating platform","Return the lost marker"],
    ["quest_tower_chimes","Chimes of the Western Tower","Hear the broken bell","Locate the bell maker","Collect suitable bronze","Repair the lifting rig","Tune the clock chimes","Ring the rebuilt tower"],
    ["quest_glass_dunes","Across the Glass Dunes","Visit the desert outpost","Prepare the shade sails","Find the buried waystones","Cross the reflective flats","Reach the cool oasis","Chart the return journey"],
    ["quest_deepwater_engine","Engine Under the Sea","Inspect the pressure gauge","Reach the submerged engine","Seal the intake valve","Replace the fractured rotor","Restart the machinery","Surface with the crew"],
    ["quest_hidden_canal","The Hidden Canal","Meet the river cartographer","Clear the old lock","Survey the culverts","Navigate the water tunnel","Open the forgotten basin","Update the city map"],
    ["quest_ember_festival","The Ember Festival","Speak with the festival host","Gather the lantern frames","Prepare safe fire bowls","Invite the hillside villages","Light the central procession","Celebrate the renewed pact"],
    ["quest_orchard_winter","Winter in the Orchard","Meet the orchard keeper","Inspect frost-damaged branches","Find sheltered seedlings","Repair the warming stones","Replant the upper terrace","Welcome the spring bloom"],
    ["quest_jade_quarry","The Jade Quarry","Receive the quarry permit","Inspect the lift mechanism","Find the hidden mineral seam","Stabilize the work ledge","Recover a carved fragment","Bring it to the workshop"],
    ["quest_bridge_of_mist","The Bridge of Mist","Study the old bridge plans","Search the misty gorge","Recover the missing stones","Secure the anchor bolts","Cross the repaired bridge","Open the valley path"],
    ["quest_river_sentinel","Sentinel of the River","Follow the damaged banks","Meet the water guardian","Find the blocked tributary","Clear the sunken debris","Restore the river flow","Record the new shoreline"],
    ["quest_northern_outpost","The Northern Outpost","Visit the remote station","Repair the radio mast","Gather the winter supplies","Rescue the stranded scout","Secure the snow trail","Send the arrival report"],
    ["quest_cavern_echos","Echoes in the Cavern","Enter the echo chamber","Map the first passage","Find the sound crystals","Cross the underground river","Repair the resonator","Return with the recorded song"],
    ["quest_sky_orchards","The Sky Orchards","Meet the island gardener","Secure the rope lifts","Gather drifting seeds","Replant the upper grove","Adjust the irrigation clouds","Celebrate the first harvest"],
    ["quest_clocktower_apprentice","Apprentice of the Clocktower","Join the clockmaker","Sort the replacement gears","Inspect the winding chamber","Build the missing escapement","Synchronize the hands","Ring the afternoon bell"],
    ["quest_wildlife_corridor","The Wildlife Corridor","Study the migration paths","Meet the forest rangers","Clear abandoned fencing","Restore the stream crossing","Observe the returning herd","Mark the protected passage"],
    ["quest_aurora_station","The Aurora Station","Locate the polar station","Calibrate the sky camera","Inspect the weather balloon","Track the aurora arc","Repair the observation array","Send the completed survey"],
    ["quest_drowned_temple","The Drowned Temple","Find the temple chart","Meet the diving team","Descend past the gate","Read the submerged inscriptions","Secure the carved tablet","Return before high tide"],
    ["quest_coral_foundry","The Coral Foundry","Find the reef workshop","Speak with the reef engineers","Locate the damaged furnace","Restore the air system","Craft a new reef anchor","Place it in shallow water"],
    ["quest_lost_weather_balloon","The Lost Weather Balloon","Receive the last position","Follow the wind forecasts","Reach the high plateau","Locate the torn envelope","Recover the instruments","Deliver the flight data"],
    ["quest_underground_orchard","Orchard Beneath the City","Locate the cellar entrance","Find the artificial sunlamps","Clear the irrigation channel","Rebuild the fungal beds","Restore the fruit garden","Open the underground market"],
    ["quest_firefly_navigation","The Firefly Navigator","Meet the lantern maker","Collect bright cave moss","Follow the firefly swarms","Find the hidden bridge","Calibrate the night route","Teach the safe crossing"],
    ["quest_solar_tide_engine","The Solar Tide Engine","Investigate the tide mill","Inspect the solar mirrors","Clear the tidal intake","Replace the cracked gear","Synchronize day and night","Restore the port power"],
    ["quest_icebound_caravan","The Icebound Caravan","Meet the caravan leader","Find the missing sled","Cross the frozen inlet","Shelter from the whiteout","Free the trapped supplies","Reach the mountain inn"],
    ["quest_treetop_council","Council in the Treetops","Receive the council summons","Repair the hanging walkways","Hear the forest delegates","Find the missing trade map","Negotiate shared access","Publish the council charter"],
    ["quest_sextant_apprentice","Lessons in the Stars","Meet the old navigator","Learn the horizon sight","Calibrate the sextant arc","Measure the noon sun","Plot the island position","Complete the celestial chart"],
    ["quest_broken_portal","The Broken Portal","Inspect the silent gateway","Find the missing anchor rune","Survey the nearby ruins","Repair the stone circuit","Stabilize the portal exit","Open the safe passage"],
    ["quest_floating_foundry","Foundry Above the Storm","Reach the floating forge","Secure the weather shields","Gather fresh mineral ore","Repair the heat ducts","Shape the replacement struts","Restore the sky platform"],
    ["quest_night_ferry","The Night Ferry","Receive the river request","Light the pier lanterns","Survey the fog channel","Rescue the delayed passengers","Repair the navigation lights","Return the ferry safely"],
    ["quest_echoes_of_the_city","Echoes of the Old City","Listen to the city bells","Find the missing historian","Explore the abandoned theater","Recover the memory recordings","Restore the public archive","Share the city's stories"],
    ["quest_moonlit_greenhouse","The Moonlit Greenhouse","Meet the greenhouse caretaker","Inspect the moon mirrors","Find the frost-resistant seeds","Repair the water pump","Restore the night blossom","Open the garden at dawn"],
    ["quest_last_skybridge","The Last Skybridge","Meet the bridge surveyors","Inspect the broken anchors","Gather the missing alloy","Install new suspension ropes","Test the windward crossing","Reopen the island route"],
)
QUEST_BLUEPRINT_ACTIONS=tuple(row[0] for row in QUEST_BLUEPRINTS)
if len(QUEST_BLUEPRINT_ACTIONS)!=50 or len(set(QUEST_BLUEPRINT_ACTIONS))!=50:
    raise RuntimeError("fifty distinct playable original quest outlines required")


def _edges(mode: int):
    """Native-quest DAG topologies: every authored stage is reachable."""
    return (
        ((1,),(2,),(3,),(4,),(5,),()),
        ((1,2),(3,),(3,),(4,),(5,),()),
        ((1,),(2,3),(4,),(5,),(),()),
        ((1,2),(3,),(4,),(5,),(5,),()),
        ((1,2),(3,),(3,),(4,),(5,),()),
        ((1,2),(3,5),(4,),(5,),(5,),()),
        ((1,3),(2,),(3,),(4,),(5,),()),
        ((1,),(2,4),(3,),(5,),(),()),
        ((1,2),(3,4),(4,),(5,),(5,),()),
        ((1,2,3),(4,),(4,),(4,),(5,),()),
    )[mode]


def edit_quest_blueprint(project: StudioProject, action: str,
                         args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in QUEST_BLUEPRINT_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unrecognized original narrative arc generator")
    number=QUEST_BLUEPRINT_ACTIONS.index(action)
    source=QUEST_BLUEPRINTS[number]
    quest_id=_name(args,"quest_id")
    event_id=_name(args,"event_id")
    if quest_id in {q.quest_id for q in project.native_quests}:
        raise StudioError("quest identity already authored")
    if event_id in {ev.event_id for ev in project.events}:
        raise StudioError("quest introductory event identity occupied")
    if not project.placements:
        raise StudioError("playable quest template requires a placed quest-giver NPC")
    target=args.get("target",f"{project.placements[0].prefab_id}:0")
    if type(target) is not str or not 1<=len(target)<=128:
        raise StudioError("bounded placed-actor interaction target required")
    if target not in {p.prefab_id+":"+str(i) for i,p in enumerate(project.placements)}:
        raise StudioError("quest starter must target a placed original-game actor")
    title=args.get("title",source[1])
    objectives=args.get("objectives",list(source[2:]))
    if (type(title) is not str or not 1<=len(title.strip())<=256 or
            type(objectives) is not list or len(objectives)!=6 or
            any(type(o) is not str or not 1<=len(o.strip())<=512 for o in objectives)):
        raise StudioError("complete original story needs title and six authored objectives")
    ids=[f"{quest_id}_scene_{i+1:02d}" for i in range(6)]
    if any(len(v)>128 for v in ids):
        raise StudioError("quest identity cannot fit stable chapter stage IDs")
    edges=_edges(number%10)
    stages=tuple(
        StudioQuestStage(ids[i],objectives[i],tuple(ids[j] for j in edges[i]))
        for i in range(6)
    )
    quest=StudioQuest(quest_id,title,ids[0],stages)
    starter=StudioEvent(event_id,"interact","",True,"start_quest",target,quest_id)
    return replace(project,native_quests=project.native_quests+(quest,),
                   events=project.events+(starter,))

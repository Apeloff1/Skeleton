"""Eight independently authored mechanic hypotheses for each environmental domain."""
ROWS = {
    "geology": [
        "Fault Listening|After placing seismic sensors|Identify dangerous stress changes|Detection resolution is finite",
        "Bedrock Exchange|When constructing over shared strata|Move stability from one region to another|Donor regions lose capacity",
        "Mineral Survey|After sampling geological layers|Reveal ore and structural conditions|Sampling can disturb fragile layers",
        "Sediment Ledger|When a river changes course|Track material moved between regions|Unrecorded losses harm downstream sites",
        "Volcanic Warning|On detecting active magma migration|Open an evacuation window|False alarms disrupt local economy",
        "Fossil Context|When extracting a fossil|Preserve exact surrounding stratigraphy|Careful removal is slower",
        "Geological Restoration|After quarry work|Rebuild soil and slope stability|Rehabilitation consumes resources",
        "Deep-Time Navigation|When traversing exposed geological eras|Link routes by formation age|Old maps may become invalid"
    ],
    "weather": [
        "Front Redirect|When pressure zones are understood|Move a storm within bounded atmospheric limits|Other settlements inherit changed weather",
        "Cloud Seeding|Under suitable moisture conditions|Increase local rainfall probability|Downwind rainfall may decline",
        "Wind Corridor|After measuring seasonal patterns|Schedule safer aerial or sea travel|Forecast uncertainty persists",
        "Weather Shelter|Before a hazardous front arrives|Construct temporary protective structures|Materials are limited",
        "Forecast Revision|When live observations disagree|Update storm tracks and warnings|Dependent plans require rework",
        "Thermal Buffer|When temperature extremes threaten|Trade stored heat across structures|Storage losses accumulate",
        "Microclimate Garden|After establishing relevant plants|Alter local humidity and shade|Plants need ongoing care",
        "Weather Aftermath|When a storm clears|Begin rebuilding with changed land topology|Damage is not reset"
    ],
    "oceans": [
        "Current Mapping|On reading temperature and salinity|Estimate a safe transport corridor|Currents keep changing",
        "Tide Window|When a crossing is planned|Schedule passage during safe water levels|Waiting changes other objectives",
        "Reef Stewardship|After reducing harmful activity|Restore navigable habitat corridors|Recovery requires seasons",
        "Deep Pressure Adapt|Before descending|Configure equipment for local pressure|Heavy insulation limits mobility",
        "Marine Treaty|When resource claims overlap|Negotiate fishing and transit permissions|Compromise limits extraction",
        "Wave Energy Ledger|On installing a barrier|Shift modeled storm surge forces|Other shorelines may be affected",
        "Salt Archive Reading|When historic water layers are sampled|Recover uncertain marine history|Contamination can distort traces",
        "Ocean Continuation|After crossing a major sea|Open ongoing stewardship and trade|New routes require maintenance"
    ],
    "forests": [
        "Root Inquiry|When a traveler listens at old trees|Read shared nutrient and hazard signals|Root messages are partial",
        "Canopy Transit|After building elevated routes|Travel without damaging the forest floor|Maintenance depends on tree health",
        "Wildfire Break|When danger rises|Coordinate ecological fire barriers|Some habitats depend on low-intensity burns",
        "Pollinator Relay|When blossoms and insects align|Propagate fertility between grove cells|Timing and species compatibility limit effect",
        "Forest Path Shift|When seasonal growth changes|Update traversable edges and hidden corridors|Old waypoints expire",
        "Silviculture Compact|Before harvesting wood|Allocate regeneration and habitat obligations|Rapid production is constrained",
        "Fungal Message|When roots connect settlements|Transmit nutrient-costly information|Communication competes with growth",
        "Old Growth Legacy|After protecting an ancient tree|Gain long-term ecological stability|Benefit arrives slowly"
    ],
    "desert": [
        "Oasis Rights|Before drawing from scarce water|Allocate transparent shares|Demand can exceed supply",
        "Sand Route|When dunes migrate|Update caravan paths with changing terrain|Maps decay quickly",
        "Shade Relay|On sharing portable shade|Create safe short-term travel pockets|Shade capacity is finite",
        "Heat Debt|During daytime labor|Accumulate fatigue requiring night recovery|Working faster harms resilience",
        "Subsurface Survey|After detecting hidden moisture|Mark sustainable extraction sites|Overuse permanently reduces availability",
        "Sandstorm Shelter|When storm onset is predicted|Secure travelers within bounded refuge areas|Some cargo must be abandoned",
        "Mirage Verify|When apparent landmarks appear|Cross-check against stable observations|Verification delays exploration",
        "Regenerative Crossing|Following an expedition|Maintain vegetation and water waypoints|Long-term care competes with exploration"
    ],
    "polar": [
        "Thermal Refuge|When extreme cold is forecast|Move shared warmth to endangered shelters|Donor buildings cool",
        "Ice Thickness Scan|Before crossing floes|Assess structural capacity|Findings expire as temperature changes",
        "Aurora Waypoint|During strong magnetic events|Reveal temporary visual routes|Visibility windows are brief",
        "Polar Night Schedule|When daylight vanishes|Reallocate farming and social activities|Energy costs increase",
        "Whale Corridor|When migrating animals approach|Open protected ocean passage|Shipping must reroute",
        "Glacier Evidence|After extracting an ice sample|Read time-layered climate signals|Sampling destroys some pristine context",
        "Thaw Mitigation|When ice destabilizes|Reinforce critical settlements or relocate|No repair is instantaneous",
        "Long-Winter Continuity|After the last mission of a season|Plan resources for indefinite winters|No final safe winter exists"
    ],
    "underground": [
        "Acoustic Survey|When visibility is low|Map tunnels from echoes|Signal quality varies with geology",
        "Ventilation Plan|Before entering a sealed cavern|Allocate breathable air and exhaust paths|Ventilation consumes energy",
        "Collapse Probe|When excavating a tunnel|Measure structural stress under load|Excessive digging raises risk",
        "Subsurface Transit|After linking safe caves|Create a route with depth lineage|Connections may become blocked",
        "Magma Bypass|When lava currents approach|Reroute passage and geothermal equipment|Alternate routes are longer",
        "Fungal Farm|Under suitable moisture|Produce cave food and oxygen support|Growth consumes substrates",
        "Ancient Shaft Recovery|After validating an old mine|Restore limited legacy infrastructure|Hidden faults may persist",
        "Deep Descent Budget|Before pursuing lower strata|Reserve ascent resources and time|Depth exploration remains unfinishable"
    ],
    "atmosphere": [
        "Pressure Balancer|When airborne settlements drift|Exchange bounded atmospheric lift|Neighboring platforms lose lift",
        "High Altitude Survey|After launching a sensor platform|Reveal uncertain sky routes|Instruments degrade in storms",
        "Cloud Corridor|When cloud density supports transit|Create temporary aerial pathways|Corridors dissolve with weather",
        "Oxygen Budget|During settlement growth|Reallocate breathable air across zones|Overcrowding lowers reserves",
        "Jetstream Intercept|When atmospheric rivers cross|Ride a predictable high-speed current|Exiting at the wrong time is costly",
        "Lightning Ground|When storms threaten|Install safe discharge paths|Equipment maintenance is essential",
        "Air Pollution Return|On detecting airborne contaminants|Track downwind responsibility and remediation|Cleanup costs resources",
        "Sky Habitat Stewardship|After locating floating ecosystems|Coordinate access and ecological limits|Airborne life is fragile"
    ]
}

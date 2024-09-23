from collections import defaultdict
from textwrap import dedent
from pathlib import Path
import sqlite3
from ck3parser import rootpath
from print_time import print_time

# light compared to cmh 1.9.2r2
#   remove MND Balance: Making empires actually work for it...
#   remove Domain to Demesne
#   remove War Alerts - Customisable War Notifications
#   remove Nameplates
#   remove Factions Explained
#   remove Displayed Birth and Death Dates
#   remove Recruit Courtiers
#   remove MONIKER
#   remove Ward Limit Based On Learning
#   remove Better AI Education
#   remove Ward Limit + Better AI Education Compatch
#   remove Knight Manager Continued
#   add Total Animation - All Portraits Are Animated
#   add More Babies For Counts & Dukes
#   remove Higher Mortality Mod
#   remove Inheritable Relations [Unfinished Business]
#   remove Ibn Battuta's Legacy; Ibn Battuta's Legacy 2 - More Cultural Names
#   remove Africa Plus [NEEDS UPDATE]; Africa Compatch (BAP + IBL); EPE + CE + BAP Compatch
#   remove Better Barbershop
#   add More Holding Graphics; MHG + EPE Compatch; MHG + CFP Compatch; MHG + CE Compatch
#   remove Entitled
#   add Gamerule Gadget
#   remove Inherichance
#   remove CMH + CTP + NPE Compatch
#   remove Ibn Battuta's Terrain Pack for CMH
#   remove CCCMH
#   remove Brighter Text Colors
#   remove Medieval Arts
#   add Patrum Scuta Expanded
#   add [DISABLED] Better Marriage (AI)
#   add Advanced Character Search
#   add Configurable News Feed - Updated
#   add Historical Marriages
#   add Lower non heterosexual orientation chance
#   add Congenital Beauty
#   add Culture Expanded - More Cultural Names
#   add Enhanced Dynasty Tree Viewer
#   add Clear Notifications
#   add Warriors without Wombs: No More Pregnant Knights!
#   add Debug Toggle (Less Invasive)
#   add (2. Checksum-invariant)
# heavy compared to light
#   add Ibn Battuta's Legacy; Ibn Battuta's Legacy 2 - More Cultural Names; Ibn Battuta's Terrain Pack for CMH
#   add Africa Plus [NEEDS UPDATE]; Africa Compatch (BAP + IBL); EPE + CE + BAP Compatch
#   remove More Holding Graphics; compatches
#   add Inherichance
#   add CCCMH
#   remove Culture Expanded - More Cultural Names
# cmh 1.12r2 compared to cmh 1.9.2r2
#   remove Fashionably Unwell: No More Sickgowns! [merged to epe]
#   add Big Battle View
#   add Raised Army CoA
#   remove Domain to Demesne
#   add Immersive Writing - Love & Romance
#   remove Factions Explained [out of date]
#   remove Title-Ranked Portrait Borders [merged to vanilla]
#   remove MONIKER [no compat with NPE though NPE's compatch isnt ready yet]
#   remove Ward Limit Based On Learning [out of date, soon to be replaced]
#   remove Better AI Education; Ward Limit + Better AI Education Compatch [out of date, soon to be replaced]
#   remove Knight Manager Continued [no compat atm]
#   add Decline Elections
#   add Pervasive Crown Authority
#   add Mass Demand Conversion
#   add More Lifestyles
#   add Alleged Infertility
#   add Holy Roman Triumph: Coronation Ceremonies
#   add Counterfactuals
#   remove Restore Carolingian Borders Fix [merged to vanilla]
#   remove Higher Mortality Mod [out of date]
#   add Medieval Arts
#   add Rescue & Vengeance
#   add Dynamic Regency
#   remove Africa Plus [NEEDS UPDATE]; Africa Compatch (BAP + IBL); EPE + CE + BAP Compatch [out of date]
#   add IBL + EPE Compatibility Patch
#   remove Entitled [dodgy update for now?]
#   add More Background Illustrations
#   add Gamerule Gadget
#   add Unified UI
#   remove Ibn Battuta's Legacy 2 - More Cultural Names [merged]
#   add Community Mods for Historicity - More Cultural Names
#   add Name Packs Expanded

# to consider adding:
#   Free Camera for Royal Court
#       probably good
#   Immersive Realm Espionage
#       idk...
#   Love Marriage Family
#   LotR: Realms in Exile
#       overhaul
#   Revert Kyiv to Kiev
#       yes (except no because we have community title project and stuff)

# fewer female rulers conflicts with mnd
# more holding graphics conflicts with more background illustrations (cmh)
# what compat issues are unsolvable without cccmh?

checksummed = {
    "common",
    "data_binding",
    "events",
    "gui",
    "history",
    "localization",
    "map_data",
}

conflict_free = {
    Path(p)
    for p in [
        ".gitattributes",
        "CHANGELOG.md",
        "descpage.info",
        "description.txt",
        "descriptor.mod",
        "LICENSE.md",
        "notes.txt",
        "README.md",
        "thumbnail_long.png",
        "thumbnail.png",
        "thumbnailwide.png",
    ]
}

# atm:
# light works, heavy crashes, apparently because of ibl, though both do have script errors
# adding bap fixes ibl.
# removing all non-cmh doesn't fix ibl.
# 100% cmh works.
# 100% cmh minus bap? crashes. w/o cccmh? crashes.
# 100% cmh minus ibl and bap? works.
# ibl by itself? works.
# so something in cmh makes ibl require bap.
# ibl,epe,ibtp,cccmh? crashes.
# ibl,ibtp,cccmh? crashes.
# ibl,cccmh? works.
# ibl,ibtp? crashes.

# more holding graphics (~cmh) and ibn battuta's legacy (cmh) seem incompatible
# heavy gets ibl, light gets mhg
# (mhg & mhg+cfp compatch go together)

# rice might be incompatible with ibl and bap without cccmh compatch, which might require bap, sinews of war, loyal to a fault, but i think it doesn't so i'm enabling it

# morven's mods added only for kg's compatch:
# Hostile Struggles, Doctor Tweak, Hagia Sophia, Pacification, Total Animation, Artifact Claims Nerf, Title-Ranked Portrait Borders

# unofficial patch goes first
# before uniui: inherichance
# in my humble opinion -> gamerule gadget -> foundational framework
# more holding graphics says: mhg+cfp -> mhg -> community flavor pack

# [not applied] At the top: Character beautification
#   > Traits
#   > Barbershop related beatification
#   > Game mechanics related to traits
#   > overall game graphics
#   > Holdings
#   > Decisions
#   > Interface
#   > Game mechanics
#   > Mechanics & Interface (culture and faith related)
#   > Total conversion Mods (bigger mods like BAP ME EPE CFP etc.)
#   > Compatches in the stated order by the authors.

# compatible_mods =
# 1. mod B is a submod for mod A
#    -> ignore all AB conflicts (keep ABx conflicts)
#    -> either load B after all other mods, or load A before all other mods (have to build dag and traverse)
# 2. mod C is a compatibility patch for mods A and B.
#    -> if ABC all in playset, ignore all AB, AC, BC, and ABC conflicts (keep ABx, ACx, BCx, ABCx conflicts)
#    should i decompose this into two instances of [1]?

# maybe instead just "these 4 mods play nice together" without bothering about whether all 4 are needed or if any subset is also fine? but then we can't generate load order nicely.

# current mod order: lexicographic on file list (heuristic for 'mod category')
#    can read tags from db, sort on tags instead. maybe better.
# mod order should be: overhauls first, then "non-framework-related", then frameworks, then framework-related?
# or... cosmetic, then mechanical?

# compatible_playsets = {
#     # "CMH 1.12 Rev2"
# }
ignore_playsets = {"Waiting for update"}
# condition, set
# (if condition mods are present, then the set mods are compatible)
compatible_sets = [
    {  # Nameplates, Unified UI
        "Nameplates",
        "Unified UI",
    },
    {  # Holy Roman Triumph
        "Holy Roman Triumph: Coronation Ceremonies",
        "The Catholic Trinity",
    },
    {  # Morven's Mods
        "Artifact Claims Nerf - No House Claims Against Dynasty",
        "Hagia Sophia & All Cathedrals Enabled For All Christians",
        "Pacification Speeds Conversion",
        "Hostile Struggles Re-Enable Holy Wars",
        "Less Sinful Priest Scandals - No More Fervour Collapse",
        "Fervour Midpoint Rebalance - Fervor Tends Towards 50%",
        "Fervour Inversion - Winning Holy Wars Increases Fervor",
        "Doctor Tweak - AI Will More Often Hire Court Physicians",
        "Less Old Wives - AI Men Marry Younger Fertile Women",
        "Morven's Mods 1.12 Compatch",
    },
    {  # Expanded Series
        "Succession Expanded",
        "Social Relations Expanded (SRE)",
        "Ethnicities and Portraits Expanded",
        "Culture Expanded",
        "Unit Packs Expanded",
        "Name Packs Expanded",
    },
    {  # SRE
        "Social Relations Expanded (SRE)",
        "Inheritable Relations",
        "Rescue & Vengeance",
        "Dynamic Regency",
        "Unified UI",
    },
    {  # Ibn Battuta's Legacy, Ibn Battuta's Terrain Pack for CMH
        "Ibn Battuta's Legacy",
        "Regional Immersion and Cultural Enrichment (RICE)",
        "Culture Expanded",
        "Ibn Battuta's Terrain Pack for CMH",
    },
    {  # RICE + EPE Compatibility Patch
        "Regional Immersion and Cultural Enrichment (RICE)",
        "Ethnicities and Portraits Expanded",
        "RICE + EPE Compatibility Patch",
    },
    {  # Culture Expanded, RICE + EPE Compatibility Patch
        "Regional Immersion and Cultural Enrichment (RICE)",
        "Culture Expanded",
        "RICE + EPE Compatibility Patch",
    },
    {  # More Background Illustrations
        "Community Flavor Pack",
        "More Background Illustrations",
    },
    {  # TCT
        "The Catholic Trinity",
        "Unified UI",
    },
    {  #
        "In My Humble Opinion",
        "Prisoners of War",
        "Inherichance",
        "Trick or Trait",
        "Unified UI",
        "Gamerule Gadget",
        "Foundational Framework",
    },
    {  # NPE
        "Regional Immersion and Cultural Enrichment (RICE)",
        "Name Packs Expanded",
    },
    {  # NPE
        "The Catholic Trinity",
        "Name Packs Expanded",
    },
    {  # CCCMH
        "MND Balance: Making empires actually work for it...",
        "CCCMH",
    },
    {  # CCCMH
        "Raised Army CoA",
        "CCCMH",
    },
    {  # CCCMH
        "Less Old Wives - AI Men Marry Younger Fertile Women",
        "CCCMH",
    },
    {  # CCCMH
        "Regional Immersion and Cultural Enrichment (RICE)",
        "Ibn Battuta's Terrain Pack for CMH",
        "CCCMH",
    },
    {  # CCCMH
        "Trick or Trait",
        "CCCMH",
    },
    {  # CMH (00_marriage_scripted_modifiers.txt)
        "MND Balance: Making empires actually work for it...",
        "Alleged Infertility",
    },
    {  # CMH (00_fervor_modifiers.txt)
        "MND Balance: Making empires actually work for it...",
        "Fervour Midpoint Rebalance - Fervor Tends Towards 50%",
    },
    {  # CMH (window_character.gui)
        "Displayed Birth and Death Dates",
        "Ethnicities and Portraits Expanded",
        "The Catholic Trinity",
        "In My Humble Opinion",
        "Unified UI",
    },
    {  # CMH (cultures)
        "Ibn Battuta's Legacy",
        "IBL + EPE Compatibility Patch",
        "Ibn Battuta's Terrain Pack for CMH",
    },
    {  # CMH (tool_property_randomizable_types.gui, toolspropertytypes.gui)
        "Ethnicities and Portraits Expanded",
        "The Catholic Trinity",
        "Trick or Trait",
        "Inherichance",
        "In My Humble Opinion",
        "Prisoners of War",
        "Gamerule Gadget",
        "Foundational Framework",
    },
    {  # CMH (fonts)
        "Culture Expanded",
        "Community Title Project",
        "Name Packs Expanded",
    },
    {  # CMH (window_barbershop.gui)
        "In My Humble Opinion",
        "Unified UI",
        "Better Barbershop",
    },
    {  # Fair Ladies, Beautiful Portraits
        "Fair Ladies",
        "Fair Lords",
        "Beautiful Portraits",
    },
    {  # Fair Ladies Expanded, Beautiful Portraits
        "Ethnicities and Portraits Expanded",
        "Fair Ladies Expanded",
        "Fair Lords Expanded",
        "Beautiful Portraits",
    },
    {  # Patrum Scuta
        "Patrum Scuta",
        "Patrum Scuta Expanded",
    },
]
conditionally_compatible_sets = [
    (
        {"CFP + EPE Compatibility Patch"},
        {
            "Community Flavor Pack",
            "Ethnicities and Portraits Expanded",
            "The Catholic Trinity",
            "Unified UI",
            "Better Barbershop",  # (window_barbershop.gui)
        },
    ),
    (
        {"CMH + CTP + NPE Compatch"},
        {
            "Ibn Battuta's Legacy",
            "Community Title Project",
            "Name Packs Expanded",
        },
    ),
    (
        {"IBL + EPE Compatibility Patch"},
        {
            "Ibn Battuta's Legacy",
            "Ethnicities and Portraits Expanded",
        },
    ),
    (
        {"CCCMH"},
        {
            "Extended Outliner",
            "Prisoners of War",
        },
    ),
]
compatible_mods = {"Unofficial Patch"}

mod_db_path = (
    Path.home() / "Documents/Paradox Interactive/Crusader Kings III/launcher-v2.sqlite"
)


@print_time
def main():
    affects_checksum = set()
    all_mods = {}
    playsets = defaultdict(list)
    mod_disabled_in_playset = set()
    con = sqlite3.connect(mod_db_path)
    for mod, path in con.execute(
        dedent(
            """\
            SELECT displayName, dirPath
            FROM mods
            WHERE status = 'ready_to_play';"""
        )
    ):
        assert mod not in all_mods
        all_mods[mod] = Path(path)
    for playset, mod, enabled in con.execute(
        dedent(
            """\
            SELECT p.name, m.displayName, pm.enabled
            FROM playsets_mods AS pm
                JOIN playsets AS p ON pm.playsetId = p.id
                JOIN mods AS m ON pm.modId = m.id
            ORDER BY p.name, pm.position;"""
        )
    ):
        if mod in all_mods:
            playsets[playset].append(mod)
            if not enabled:
                mod_disabled_in_playset.add((playset, mod))
        else:
            print(f"[WARN] not ready: {mod}")
    con.close()
    # conditionally_compatible_sets.extend(
    #     (set(), set(playsets[p])) for p in compatible_playsets
    # )
    mods_of_files = defaultdict(set)
    files_of_mod = defaultdict(list)
    playset_conflicts = {}
    for mod, mod_path in all_mods.items():
        for path, dirnames, filenames in mod_path.walk():
            if ".git" in dirnames:
                dirnames.remove(".git")
            for filename in filenames:
                file = (path / filename).relative_to(mod_path)
                mods_of_files[file].add(mod)
                files_of_mod[mod].append(file)
                if file.parts[0] in checksummed:
                    affects_checksum.add(mod)
    for playset, playset_mods in playsets.items():
        if playset in ignore_playsets:
            continue
        playset_mods_set = set(playset_mods)
        playset_compatible_sets = compatible_sets + [
            s | c for c, s in conditionally_compatible_sets if playset_mods_set >= c
        ]
        playset_conflicts[playset] = defaultdict(list)
        for file, file_mods in mods_of_files.items():
            # order has been discarded but we want to be able to check it
            mods = file_mods.intersection(playset_mods) - compatible_mods
            if (
                len(mods) > 1
                and not any(s >= mods for s in playset_compatible_sets)
                and conflict_free.isdisjoint({file, *file.parents})
            ):
                playset_conflicts[playset][frozenset(mods)].append(file)

    for playset, playset_mods in playsets.items():
        filename = "_".join(s for s in playset.split())
        filename = "".join(c for c in filename if c.isalnum() or c in "_-.")
        with open(f"ck3_playset_{filename}.txt", "w", encoding="utf8") as f:
            for mod in playset_mods:
                disabled = (playset, mod) in mod_disabled_in_playset
                print(f"{"[DISABLED] " if disabled else ""}{mod}", file=f)

    with open(rootpath / "ck3_mod_conflicts.txt", "w", encoding="utf8") as f:
        print("Checksum-invariant mods:", file=f)
        for mod in sorted(all_mods):
            if mod not in affects_checksum:
                print(f"\t{mod}", file=f)
        for playset, conflicts in sorted(playset_conflicts.items()):
            print(playset, file=f)
            if not conflicts:
                print("\t<no conflicts>", file=f)
            conflicts_sorted = sorted(
                (
                    (sorted(mods, key=playsets[playset].index), sorted(files))
                    for mods, files in conflicts.items()
                ),
                key=(lambda p: [playsets[playset].index(m) for m in p[0]]),
            )
            for mods, files in conflicts_sorted:
                print("\t" + "; ".join(mods), file=f)
                for file in files:
                    print(f"\t\t{file.as_posix()}", file=f)


if __name__ == "__main__":
    main()

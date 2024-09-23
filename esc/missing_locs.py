#!/usr/bin/env python3

from pathlib import Path
import re
import sys
from ck2parser import Obj, SimpleParser, get_localisation, rootpath
from print_time import print_time

# auditing tool for missing localisations.
# unfinished, stopped during societies
# applied to geheimnisnacht


MIN_SEVERITY = 1

SEVERITY_1 = 1
SEVERITY_2 = 2
SEVERITY_3 = 3


def check(result, locs, severity, key):
    if (
        key not in locs
        and severity >= MIN_SEVERITY
        and key not in result
        and " " not in key
    ):
        result.append(key)


def check_trigger(result, locs, trigger):
    def recurse(v):
        for n2, v2 in v:
            if isinstance(v2, Obj):
                recurse(v2)
            elif n2.val in {
                "text",
                "localisation_key",
                "desc",
                "has_offmap_name",
                "has_had_offmap_name",
            }:
                check(result, locs, SEVERITY_2, v2.val)

    recurse(trigger)


def check_effect(result, locs, effect):
    def recurse(v, n=None):
        for n2, v2 in v:
            if isinstance(v2, Obj):
                if n2.val in {
                    "limit",
                    "trigger",
                    "modifier",
                    "mult_modifier",
                    "additive_modifier",
                    "additive_exported_value_modifier",
                    "additive_opinion_modifier",
                    "additive_power_diff_modifier",
                    "additive_compared_realm_size_modifier",
                    "additive_realm_size_modifier",
                }:
                    check_trigger(result, locs, v2)
                elif n2.val != "troops":
                    if n2.val in {
                        "add_character_modifier",
                        "add_province_modifier",
                        "add_holding_modifier",
                        "add_society_modifier",
                    } and not v2.has_pair("hidden", "yes"):
                        modifier = v2.get("modifier", v2.get("name")).val
                        check(result, locs, SEVERITY_2, modifier)
                    recurse(v2, n2.val)
            elif (
                n2.val
                in {
                    "set_name",
                    "text",
                    "key",
                    "localisation",
                    "tooltip",
                    "name_list",
                    "add_evil_god_name",
                    "add_god_name",
                    "adjective",
                    "set_dynasty_name",
                    "set_high_god_name",
                    "set_offmap_name",
                    "set_special_character_title",
                }
                or n == "create_title"
                and n2.val in {"name", "ruler", "ruler_female", "foa"}
            ):
                check(result, locs, SEVERITY_2, v2.val)
            elif (
                n2.val
                in {
                    "set_description",
                    "origin_description",
                    "add_custom_history",
                }
                or n == "chronicle"
                and n2.val in {"entry", "type"}
            ):
                check(result, locs, SEVERITY_1, v2.val)

    recurse(effect)


def check_alternate_start(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/alternate_start/*.txt"):
        result = []
        for n, v in tree:
            if v.get("type"):  # setting
                setting = f"setting_{n.val}"
                check(result, locs, SEVERITY_2, setting)
                check(result, locs, SEVERITY_1, f"{setting}_tooltip")
                for n2, v2 in v:
                    if isinstance(v2, Obj):
                        if n2.val in {"potential", "trigger"}:
                            check_trigger(result, locs, v2)
                        else:
                            if n2.val not in {"checked", "unchecked"}:
                                option = f"{setting}_{n2.val}"
                                check(result, locs, SEVERITY_2, option)
                                check(result, locs, SEVERITY_2, f"{option}_tooltip")
                            if effect := v2.get("effect"):
                                check_effect(result, locs, effect)
            elif n.val == "religion_name_formats":
                for n2, v2 in v:
                    for n3 in v2:
                        check(result, locs, SEVERITY_2, n3.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_artifact_spawns(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/artifact_spawns/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                if n2.val in {"spawn_chance", "weight"}:
                    check_trigger(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_artifacts(parser, locs):
    unused = [
        r"ring_of_(luck|insight)",
        r"asur_steel_armour",
        r"Siegebreaker",
        r"Gut_Blade",
        r"Gut_Plate",
        r"\w+_flagship",
        r"nagash_crown",
    ]
    dynamic = [
        r"sword_\d_battlefield_upgraded",
        r"asur_ithilmar_(sword|battleaxe)",
        r"dawi_axe",
    ]
    dynamic_desc = [r"antiquity_book_\w+"]
    folder_result = {}
    for path, tree in parser.parse_files("common/artifacts/*.txt"):
        result = []
        for n, v in tree:
            if n.val == "slots":
                for n2, _ in v:
                    check(result, locs, SEVERITY_2, n2.val)
            elif not any(re.fullmatch(p, n.val) for p in unused):
                for n2, v2 in v:
                    if n2.val in {"active", "allowed_gift"}:
                        check_trigger(result, locs, v2)
                if not any(re.fullmatch(p, n.val) for p in dynamic):
                    artifact = n.val
                    check(result, locs, SEVERITY_2, artifact)
                    if not any(re.fullmatch(p, artifact) for p in dynamic_desc):
                        check(result, locs, SEVERITY_1, f"{artifact}_desc")
        if result:
            folder_result[path.name] = result
    return folder_result


def check_bloodlines(parser, locs):
    unused = [
        r"chaos_dwarf_sorcerer_statue_bloodline",
        r"rasul",
        r"miragliano_miracle_bloodline",
    ]
    dynamic = [
        r"saintly_bloodline_\w+_\d+",
        r"ancestor_worship_bloodline_\d+",
        r"legendary_\w+",
    ]
    dynamic_desc = [
        r"great_conqueror_\w+",
        r"random_world_bloodline_\w+",
        r"saintly_bloodline_07",
        r"samrat_chakravartin_\w+",
        r"saoshyant_\w+",
        r"israel_\w+",
        r"roman_emperor_\w+",
        r"phalaris_male",
        r"teuta_female",
        r"child_of_destiny_\w+",
    ]
    folder_result = {}
    for path, tree in parser.parse_files("common/bloodlines/*.txt"):
        result = []
        for n, v in tree:
            if not any(re.fullmatch(p, n.val) for p in unused):
                if trigger := v.get("active"):
                    check_trigger(result, locs, trigger)
                if not any(re.fullmatch(p, n.val) for p in dynamic):
                    bloodline = n.val
                    check(result, locs, SEVERITY_2, bloodline)
                    if not any(re.fullmatch(p, bloodline) for p in dynamic_desc):
                        check(result, locs, SEVERITY_1, f"{bloodline}_desc")
        if result:
            folder_result[path.name] = result
    return folder_result


def check_bookmarks(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/bookmarks/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                if n2.val in {"name", "desc"}:
                    check(result, locs, SEVERITY_3, v2.val)
                elif n2.val == "selectable_character":
                    for n3, v3 in v2:
                        if n3.val in {"name", "title_name"}:
                            check(result, locs, SEVERITY_3, v3.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_buildings(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/buildings/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                check(result, locs, SEVERITY_2, n2.val)
                for n3, v3 in v2:
                    if n3.val == "desc":
                        check(result, locs, SEVERITY_2, v3.val)
                    elif n3.val in {"potential", "trigger", "is_active_trigger"}:
                        check_trigger(result, locs, v3)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_cb_types(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/cb_types/*.txt"):
        result = []
        for n, v in tree:
            for n2, v2 in v:
                if n2.val in {"name", "war_name"}:
                    check(result, locs, SEVERITY_2, v2.val)
                elif n2.val in {
                    "can_use",
                    "can_use_title",
                    "can_use_gui",
                    "is_valid",
                    "is_valid_title",
                    "ai_will_do",
                }:
                    check_trigger(result, locs, v2)
                elif n2.val in {
                    "on_add",
                    "on_add_title",
                    "on_add_posttitle",
                    "on_success",
                    "on_success_title",
                    "on_success_posttitle",
                    "on_fail",
                    "on_fail_title",
                    "on_fail_posttitle",
                    "on_reverse_demand",
                    "on_reverse_demand_title",
                    "on_reverse_demand_posttitle",
                    "on_attacker_leader_death",
                    "on_defender_leader_death",
                    "on_thirdparty_death",
                }:
                    check_effect(result, locs, v2)
        check(result, locs, SEVERITY_1, f"{n.val}_desc")
        if result:
            folder_result[path.name] = result
    return folder_result


def check_combat_tactics(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/combat_tactics/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            check_trigger(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_council_positions(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/council_positions/*.txt"):
        result = []
        for n, v in tree:
            position = n.val
            check(result, locs, SEVERITY_2, position)
            check(result, locs, SEVERITY_1, f"{position}_desc")
            for n2, v2 in v:
                if n2.val in {"potential", "selection", "war_target"}:
                    check_trigger(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_council_voting(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/council_voting/*.txt"):
        result = []
        check_trigger(result, locs, tree)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_cultures(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/cultures/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            for n2, v2 in v:
                if n2.val == "alternate_start":
                    check_trigger(result, locs, v2)
                elif n2.val not in {"graphical_cultures", "unit_graphical_cultures"}:
                    check(result, locs, SEVERITY_2, n2.val)
                    if trigger := v2.get("alternate_start"):
                        check_trigger(result, locs, trigger)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_death(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/death/*.txt"):
        result = []
        for _, v in tree:
            check(result, locs, SEVERITY_2, v.get("long_desc").val)
            if death_date_desc := v.get("death_date_desc"):
                check(result, locs, SEVERITY_2, death_date_desc.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_death_text(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/death_text/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            check_trigger(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_disease(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/disease/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            for n2, v2 in v:
                if n2.val in {
                    "effect",
                    "yearly_province_pulse",
                    "on_character_infection",
                    "on_province_infection",
                }:
                    check_effect(result, locs, v2)
                elif n2.val == "character_infection_chances":
                    check_trigger(result, locs, v2)
                elif n2.val == "tooltip":
                    check(result, locs, SEVERITY_2, v2.val)
                elif n2.val == "timeperiod" and (trigger := v2.get("can_outbreak")):
                    check_trigger(result, locs, trigger)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_event_modifiers(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/event_modifiers/*.txt"):
        result = []
        check_trigger(result, locs, tree)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_execution_methods(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/execution_methods/*.txt"):
        result = []
        check_trigger(result, locs, tree)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_game_rules(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/game_rules/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                if n2.val in {"name", "desc", "group"}:
                    check(result, locs, SEVERITY_3, v2.val)
                elif n2.val == "option":
                    for n3, v3 in v2:
                        if n3.val in {"text", "desc"}:
                            check(result, locs, SEVERITY_2, v3.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_government_flavor(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/government_flavor/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                if n2.val == "name":
                    check(result, locs, SEVERITY_2, v2.val)
                elif n2.val == "trigger":
                    check_trigger(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_governments(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/governments/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                government = n2.val
                check(result, locs, SEVERITY_2, government)
                check(result, locs, SEVERITY_2, f"{government}_desc")
                if trigger := v2.get("potential"):
                    check_trigger(result, locs, trigger)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_heir_text(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/heir_text/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            check_trigger(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_holding_types(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/holding_types/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            check_trigger(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_job_actions(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/job_actions/*.txt"):
        result = []
        for n, v in tree:
            action = n.val
            check(result, locs, SEVERITY_2, action)
            check(result, locs, SEVERITY_1, f"{action}_desc")
            for n2, v2 in v:
                if n2.val in {"potential", "trigger"}:
                    check_trigger(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_job_titles(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/job_titles/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            for n2, v2 in v:
                if n2.val in {"allow", "dismiss_trigger"}:
                    check_trigger(result, locs, v2)
                if n2.val in {"gain_effect", "lose_effect", "retire_effect"}:
                    check_effect(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_landed_titles(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/landed_titles/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_3, n.val)
            if trigger := v.get("allow"):
                check_trigger(result, locs, trigger)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_laws(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/laws/*.txt"):
        result = []
        for n, v in tree:
            for n2, v2 in v:
                law = n2.val
                check(result, locs, SEVERITY_2, law)
                check(result, locs, SEVERITY_2, f"{law}_desc")
                if n.val != "law_groups":
                    for n3, v3 in v2:
                        if isinstance(v3, Obj):
                            if n3.val == "effect":
                                check_effect(result, locs, v3)
                            else:
                                check_trigger(result, locs, v3)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_minor_titles(parser, locs):
    no_name = [r"title_ruler_consort"]
    unused = [r"title_genghis", r"title_baba"]
    folder_result = {}
    for path, tree in parser.parse_files("common/minor_titles/*.txt"):
        result = []
        for n, v in tree:
            if not any(re.fullmatch(p, n.val) for p in no_name + unused):
                check(result, locs, SEVERITY_2, n.val)
            for n2, v2 in v:
                if n2.val in {"allowed_to_hold", "allowed_to_grant", "revoke_trigger"}:
                    check_trigger(result, locs, v2)
                elif n2.val in {
                    "gain_effect",
                    "lose_effect",
                    "retire_effect",
                    "death_effect",
                }:
                    check_effect(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_modifier_definitions(parser, locs):
    unused = [
        r"aggression",
        r"saintly_(cardinal|papal|priest_chaplain|personal_chaplain|indulgement|holy_men)_bloodline",
        r"wonder_upgrade_intimidation",
        r"(fimir|skaven_main|eshin|moulder|pestilens|skryre|skaven_black|skaven_white|creature_snotling|creature_skaven)_opinion",
        r"upgrade_(new_temple_buildings_special|aerodrome_capital_only)_effect",
    ]
    folder_result = {}
    for path, tree in parser.parse_files("common/modifier_definitions/*.txt"):
        result = []
        for n, _ in tree:
            if not any(re.fullmatch(p, n.val) for p in unused):
                check(result, locs, SEVERITY_2, n.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_nicknames(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/nicknames/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            check_trigger(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_objectives(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/objectives/*.txt"):
        result = []
        for n, v in tree:
            objective = n.val
            check(result, locs, SEVERITY_2, f"{objective}_title")
            check(result, locs, SEVERITY_1, f"{objective}_desc")
            for n2, v2 in v:
                if n2.val in {
                    "potential",
                    "player_allow",
                    "target_potential",
                    "allow",
                    "allow_join",
                    "chance",
                    "success",
                    "abort",
                    "membership",
                }:
                    check_trigger(result, locs, v2)
                elif n2.val in {"abort_effect", "effect", "creation_effect"}:
                    check_effect(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_offmap_powers(parser, locs):
    dynamic_name = [r"undivided_warp"]
    no_currency = [r"offmap_the_lady"]
    unused_modifiers = [r"warp_(\w+_invasion|ascendant|united)"]
    folder_result = {}
    for path, tree in parser.parse_files("common/offmap_powers/*.txt"):
        result = []
        for n, v in tree:
            for n2, v2 in v:
                if n2.val == "name":
                    if not any(re.fullmatch(p, n.val) for p in dynamic_name):
                        check(result, locs, SEVERITY_2, v2.val)
                if n2.val == "currency_name":
                    if not any(re.fullmatch(p, n.val) for p in no_currency):
                        check(result, locs, SEVERITY_2, v2.val)
                elif n2.val in {
                    "display_trigger",
                    "buttons",
                    "icon_triggers",
                    "monthly_currency_gain",
                    "holder_succession",
                    "diplomatic_range",
                }:
                    check_trigger(result, locs, v2)
        if result:
            folder_result[path.name] = result
    for path, tree in parser.parse_files("common/offmap_powers/*/*.txt"):
        result = []
        for n, v in tree:
            modifier = n.val
            if not any(re.fullmatch(p, modifier) for p in unused_modifiers):
                check(result, locs, SEVERITY_2, modifier)
                check(result, locs, SEVERITY_2, f"{modifier}_desc")
                check(result, locs, SEVERITY_2, f"{modifier}_effect_desc")
        if result:
            folder_result[path.relative_to(path.parents[1]).as_posix()] = result
    return folder_result


def check_opinion_modifiers(parser, locs):
    unused = [
        r"opinion_intimidated",
        r"opinion_melee_spectator",
        r"skaven_invading_me",
        r"opinion_refused_request_mercenary",
    ]
    folder_result = {}
    for path, tree in parser.parse_files("common/opinion_modifiers/*.txt"):
        result = []
        for n, v in tree:
            if (
                (opinion := v.get("opinion"))
                and opinion.val != 0
                and not any(re.fullmatch(p, n.val) for p in unused)
            ):
                check(result, locs, SEVERITY_2, n.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_religion_features(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/religion_features/*.txt"):
        result = []
        for _, v in tree:
            for n2, v2 in v:
                if n2.val != "buttons":
                    feature = n2.val
                    check(result, locs, SEVERITY_2, feature)
                    check(result, locs, SEVERITY_1, f"{feature}_desc")
                    for n3, v3 in v2:
                        if n3.val in {"potential", "trigger", "ai_will_do"}:
                            check_trigger(result, locs, v3)
                        elif n3.val == "effect":
                            check_effect(result, locs, v3)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_religion_modifiers(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/religion_modifiers/*.txt"):
        result = []
        for n, _ in tree:
            check(result, locs, SEVERITY_2, n.val)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_religions(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/religions/*.txt"):
        result = []
        for n, v in tree:
            if n.val == "secret_religion_visibility_trigger":
                check_trigger(result, locs, v)
            else:
                check(result, locs, SEVERITY_2, n.val)
                for n2, v2 in v:
                    if isinstance(v2, Obj) and n2.val not in {
                        "color",
                        "interface_skin",
                        "male_names",
                        "female_names",
                    }:
                        religion = n2.val
                        check(result, locs, SEVERITY_2, religion)
                        check(result, locs, SEVERITY_1, f"{religion}_DESC")
                        for n3, v3 in v2:
                            if n3.val in {
                                "crusade_name",
                                "scripture_name",
                                "priest_title",
                                "high_god_name",
                            }:
                                check(result, locs, SEVERITY_2, v3.val)
                            elif n3.val in {"god_names", "evil_god_names"}:
                                for n4 in v3:
                                    check(result, locs, SEVERITY_2, n4.val)
                            elif n3.val == "unit_modifier":
                                check_effect(result, locs, v3)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_religious_titles(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/religious_titles/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            for n2, v2 in v:
                if n2.val in {"allowed_to_grant", "allow"}:
                    check_trigger(result, locs, v2)
                elif n2.val in {"gain_effect", "lose_effect"}:
                    check_effect(result, locs, v2)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_retinue_subunits(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/retinue_subunits/*.txt"):
        result = []
        for n, v in tree:
            check(result, locs, SEVERITY_2, n.val)
            if trigger := v.get("potential"):
                check_trigger(result, locs, trigger)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_scripted_effects(parser, locs):
    unused = [r"this_is_becoming_\w+_effect"]
    folder_result = {}
    for path, tree in parser.parse_files("common/scripted_effects/*.txt"):
        result = []
        for n, v in tree:
            if not any(re.fullmatch(p, n.val) for p in unused):
                check_effect(result, locs, v)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_scripted_score_values(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/scripted_score_values/*.txt"):
        result = []
        check_trigger(result, locs, tree)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_scripted_triggers(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/scripted_triggers/*.txt"):
        result = []
        check_trigger(result, locs, tree)
        if result:
            folder_result[path.name] = result
    return folder_result


def check_societies(parser, locs):
    folder_result = {}
    for path, tree in parser.parse_files("common/societies/*.txt"):
        result = []
        for n, v in tree:
            society = n.val
            check(result, locs, SEVERITY_2, society)
            check(result, locs, SEVERITY_1, f"{society}_desc")
            check(result, locs, SEVERITY_1, f"{society}_leader_desc")
            for n2, v2 in v:
                if n2.val in {
                    "non_interference",
                    "active",
                    "can_join_society",
                    "show_society",
                    "potential",
                    "startup_populate",
                }:
                    check_trigger(result, locs, v2)
                elif n2.val == "monthly_currency_gain":
                    for n3, v3 in v2:
                        if n3.val == "name":
                            check(result, locs, SEVERITY_2, v3.val)
                        elif n3.val == "triggered_gain":
                            check_trigger(result, locs, v3)
                elif n2.val == "society_rank":
                    for n3, v3 in v2:
                        if n3.val == "level":
                            rank = f"{society}_rank_{v3.val}"
                            check(result, locs, SEVERITY_2, f"{rank}_male")
                            check(result, locs, SEVERITY_2, f"{rank}_female")
                        elif n3.val == "custom_tooltip":
                            check(result, locs, SEVERITY_2, v3.val)
        # todo quests, dynamic secret religious society
        if result:
            folder_result[path.name] = result
    return folder_result


# history
#   create_bloodline scope
#     name = loc_key
#     desc = loc_key
#   offmap title scope
#     name = loc_key

# parse localisation values for [] stuff? color stuff?
#   variables that are referenced in [.GetName] need loc..
# interface/messagetypes.txt

# maybe come up with better way to handle things that are unused in mod but not in vanilla...


@print_time
def main():
    results = {}
    parser = SimpleParser(*map(Path, sys.argv[1:]))
    exceptions = {
        k: None
        for k in [
            "",
            "PIETY",
            "Gaozu",
            "Taizu",
            "Shizu",
            "Zhaozu",
            "Jingzu",
            "Xianzu",
            "Liezu",
            "Chengzu",
            "Magne",
        ]
    }
    locs = get_localisation(parser.moddirs) | exceptions

    results["common/alternate_start"] = check_alternate_start(parser, locs)
    results["common/artifact_spawns"] = check_artifact_spawns(parser, locs)
    results["common/artifacts"] = check_artifacts(parser, locs)
    results["common/bloodlines"] = check_bloodlines(parser, locs)
    results["common/bookmarks"] = check_bookmarks(parser, locs)
    results["common/buildings"] = check_buildings(parser, locs)
    results["common/cb_types"] = check_cb_types(parser, locs)
    results["common/combat_tactics"] = check_combat_tactics(parser, locs)
    results["common/council_positions"] = check_council_positions(parser, locs)
    results["common/council_voting"] = check_council_voting(parser, locs)
    results["common/death"] = check_death(parser, locs)
    results["common/death_text"] = check_death_text(parser, locs)
    results["common/disease"] = check_disease(parser, locs)
    results["common/event_modifiers"] = check_event_modifiers(parser, locs)
    results["common/execution_methods"] = check_execution_methods(parser, locs)
    results["common/game_rules"] = check_game_rules(parser, locs)
    results["common/government_flavor"] = check_government_flavor(parser, locs)
    results["common/governments"] = check_governments(parser, locs)
    results["common/heir_text"] = check_heir_text(parser, locs)
    results["common/holding_types"] = check_holding_types(parser, locs)
    results["common/job_actions"] = check_job_actions(parser, locs)
    results["common/job_titles"] = check_job_titles(parser, locs)
    results["common/landed_titles"] = check_landed_titles(parser, locs)
    results["common/laws"] = check_laws(parser, locs)
    results["common/minor_titles"] = check_minor_titles(parser, locs)
    results["common/modifier_definitions"] = check_modifier_definitions(parser, locs)
    results["common/nicknames"] = check_nicknames(parser, locs)
    results["common/objectives"] = check_objectives(parser, locs)
    results["common/offmap_powers"] = check_offmap_powers(parser, locs)
    results["common/opinion_modifiers"] = check_opinion_modifiers(parser, locs)
    results["common/religion_features"] = check_religion_features(parser, locs)
    results["common/religion_modifiers"] = check_religion_modifiers(parser, locs)
    results["common/religions"] = check_religions(parser, locs)
    results["common/religious_titles"] = check_religious_titles(parser, locs)
    results["common/retinue_subunits"] = check_retinue_subunits(parser, locs)
    results["common/scripted_effects"] = check_scripted_effects(parser, locs)
    results["common/scripted_score_values"] = check_scripted_score_values(parser, locs)
    results["common/scripted_triggers"] = check_scripted_triggers(parser, locs)
    results["common/societies"] = check_societies(parser, locs)

    modnames = "".join(x.name.lower() + "_" for x in parser.moddirs)
    with (rootpath / f"{modnames}missing_locs.txt").open("w") as f:
        if not any(results.values()):
            print(f"(none at severity >= {MIN_SEVERITY})", file=f)
        for folder, folder_results in results.items():
            if folder_results:
                print(folder, file=f)
            for file, file_results in folder_results.items():
                if file_results:
                    print(f"\t{file}", file=f)
                for key in file_results:
                    print(f"\t\t{key}", file=f)


if __name__ == "__main__":
    main()

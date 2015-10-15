
#include "an_province.h"
#include "default_map.h"
#include "definitions_table.h"
#include "pdx.h"
#include "error.h"

#include <boost/filesystem.hpp>

#include <cstdio>
#include <cerrno>
#include <cstring>
#include <vector>
#include <algorithm>

using namespace boost::filesystem;

const path VROOT_DIR("D:/SteamLibrary/steamapps/common/Crusader Kings II");
const path ROOT_DIR("D:/g/SWMH-BETA/SWMH");
const path DEFAULT_OUTPUT_PATH("./emf_nomad_codegen.txt");
const bool OUTPUT_HISTORY_DATA = false; // debugging data to stderr re: history execution
const uint END_YEAR = 1337;

//const std::vector< std::pair<uint, uint> > UNPLAYABLE_YEAR_RANGES = { {0, 769}, {769, 867}, {867, 1000}, {1000, 1066}, };
//const std::vector< std::pair<uint, uint> > UNPLAYABLE_YEAR_RANGES = { {0, 769}, {769, 867}, {867, 1066}, };
const std::vector< std::pair<uint, uint> > UNPLAYABLE_YEAR_RANGES = { {0, 867}, {867, 1066}, };

void execute_province_history(const default_map&, const definitions_table&, an_province**);
void write_main_event(FILE*, an_province** prov_map, uint map_sz);

void print_block(int indent, const pdx::block*);
void print_stmt(int indent, const pdx::stmt&);
void print_obj(int indent, const pdx::obj&);

int main(int argc, char** argv) {

    path output_path = DEFAULT_OUTPUT_PATH;

    if (argc >= 2)
        output_path = path(argv[1]);

    try {
        default_map dm(ROOT_DIR);
        definitions_table def_tbl(dm);

        uint prov_map_sz = dm.max_province_id() + 1;
        an_province** prov_map = new an_province*[prov_map_sz];
        for (uint i = 0; i < prov_map_sz; ++i) prov_map[i] = nullptr;

        execute_province_history(dm, def_tbl, prov_map);

        FILE* of = fopen(output_path.c_str(), "wb");

        if (of == nullptr)
            throw va_error("could not open event output file: %s: %s",
                           strerror(errno), output_path.c_str());

        write_main_event(of, prov_map, prov_map_sz);

        for (uint i = 1; i < prov_map_sz; ++i)
            if (prov_map[i])
                prov_map[i]->write_event(of);

        fclose(of);
    }
    catch (std::exception& e) {
        fprintf(stderr, "fatal: %s\n", e.what());
        return 1;
    }

    return 0;
}



bool block_has_title_stmt(const pdx::block& block) {
    for (auto&& s : block.stmt_list)
        if (s.key_eq("title"))
            return true;
    return false;
}


struct hist_record {
    pdx::date_t date;
    const char* cul;
    const char* rel;
    bool is_holy;

    hist_record(pdx::date_t d)
        : date(d), cul(nullptr), rel(nullptr), is_holy(false) {}

    bool operator<(const hist_record& e) const noexcept { return date < e.date; }
};


bool process_hist_record(const pdx::block* p_block, std::vector<hist_record>& records) {

    hist_record& r = records.back();

    for (auto&& s : p_block->stmt_list) {
        if (s.key.is_c_str()) {
            const char* key = s.key.c_str();

            if (strcasecmp(key, "culture") == 0)
                r.cul = s.val.as_c_str();
            else if (strcasecmp(key, "religion") == 0)
                r.rel = s.val.as_c_str();
        }
        else if (s.key.is_title()) {
            assert( pdx::title_tier(s.key.title()) == pdx::TIER_BARON );

            if (s.val.is_integer()) {
                // e.g., b_roma = 0
                assert( s.val.integer() == 0 );
            }
            else {
                const char* holding_type = s.val.as_c_str();

                if (strcasecmp(holding_type, "temple") == 0)
                    r.is_holy = true;
            }
        }
    }

    return (r.cul || r.rel || r.is_holy);
}


uint round_date_to_playable_year(pdx::date_t d) {
    uint y = d.year();

    /* check if the year is unplayable, and if so, round up to the next playable year. */

    for (auto&& r : UNPLAYABLE_YEAR_RANGES)
        if (y > r.first && y < r.second)
            return r.second;

    return y;
}


void execute_province_history(const default_map& dm,
                              const definitions_table& def_tbl,
                              an_province** prov_map) {

    path prov_hist_root = ROOT_DIR / "history/provinces";
    path prov_hist_vroot = VROOT_DIR / "history/provinces";

    char filename[256];
    uint id = 0;

    for (auto&& def : def_tbl.row_vec) {
        ++id;

        if (dm.id_is_seazone(id)) // sea | major river
            continue;

        if (def.name.empty()) // wasteland | external
            continue;

        sprintf(filename, "%u - %s.txt", id, def.name.c_str());

        path prov_hist_file = prov_hist_root / filename;

        if (!exists(prov_hist_file)) {
            path prov_hist_vfile = prov_hist_vroot / filename;

            if (!exists(prov_hist_vfile))
                throw va_error("could not find province history file: %s", filename);
            else
                prov_hist_file = prov_hist_vfile;
        }

        pdx::plexer lex(prov_hist_file.c_str());
        pdx::block doc(lex, true);

        /* ensure that this province history file has an associated county title,
         * else skip it, because it's wasteland or something. */

        if (!block_has_title_stmt(doc))
            continue;

        std::vector<hist_record> records;

        /* scan top-level... */

        static const pdx::date_t EPOCH = { 1, 1, 1 };
        records.emplace_back(EPOCH);
        process_hist_record(&doc, records);

        if (!records.front().cul)
            throw va_error("province %u lacks a top-level culture assignment: %s",
                           id, prov_hist_file.c_str());

        if (!records.front().rel)
            throw va_error("province %u lacks a top-level religion assignment: %s",
                           id, prov_hist_file.c_str());

        /* scan history entries... */

        for (auto&& s : doc.stmt_list) {
            if (!s.key.is_date())
                continue;

            pdx::date_t date = s.key.date();

            if (date.year() > END_YEAR)
                continue; // skip history records that can never have an effect

            records.emplace_back(date);
            if (!process_hist_record(s.val.as_block(), records))
                records.pop_back(); // n/m, the entry didn't contain any relevant info

        }

        // history records are possibly out-of-order, so fix that now.
        std::sort(records.begin(), records.end());

        assert( !records.empty() ); // seriously.

        /* some useful debugging output... */

        if (OUTPUT_HISTORY_DATA) {
            fprintf(stderr, "=======================================================\n");
            fprintf(stderr, "ID %u (%s):\n", id, def.name.c_str());

            for (auto&& r : records) {
                printf("  %hu.%hhu.%hhu:\n", r.date.y, r.date.m, r.date.d);

                if (r.cul)
                    printf("    culture:  %s\n", r.cul);
                if (r.rel)
                    printf("    religion: %s\n", r.rel);
                if (r.is_holy)
                    printf("    temple\n");
            }
        }

        /* build a merged (start year, culture, religion, has_temple) level table... */

        uint cw_year = round_date_to_playable_year(records.front().date); // current working year
        const char* cul = nullptr;
        const char* rel = nullptr;
        bool is_holy = false;

        prov_map[id] = new an_province(id, def.name);
        an_province& prov = *prov_map[id];

        for (auto&& r : records) {
            uint year = round_date_to_playable_year(r.date);

            if (year > cw_year) {
                /* output current working state to an an_provice::hist_entry */
                prov.hist_list().emplace_back(cw_year, cul, rel, is_holy);
                cw_year = year;
            }

            if (r.cul)
                cul = r.cul;
            if (r.rel)
                rel = r.rel;
            if (r.is_holy)
                is_holy = true;
        }

        /* output the last hist_entry (it will never be output in the above loop,
         * but our current working state will reflect it). note that this could even
         * be last = first with the above loop having output nothing at all. */
        prov.hist_list().emplace_back(round_date_to_playable_year(records.back().date),
                                      cul, rel, is_holy);

        if (OUTPUT_HISTORY_DATA) {
            fprintf(stderr, "------------------------------------------------------+\n");
            fprintf(stderr, "%4s | %17s | %18s | HOLY? |\n", "YEAR", "CULTURE", "RELIGION");

            for (auto&& e : prov.hist_list()) {
                printf("%4u | %17s | %18s | %s     |\n",
                       e.year, e.culture.c_str(), e.religion.c_str(),
                       (e.has_temple) ? "Y" : "N");
            }

            fprintf(stderr, "------------------------------------------------------+\n\n\n");
        }
    }
}


void write_main_event(FILE* f, an_province** prov_map, uint prov_map_sz) {

}


void print_block(int indent, const pdx::block* p_b) {
    for (auto&& s : p_b->stmt_list)
        print_stmt(indent, s);
}


void print_stmt(int indent, const pdx::stmt& s) {
    printf("%*s", indent, "");
    print_obj(indent, s.key);
    printf(" = ");
    print_obj(indent, s.val);
    printf("\n");
}


void print_obj(int indent, const pdx::obj& o) {

    using namespace pdx;

    if (o.type == obj::STR) {
        if (!strchr(o.data.s, ' ')) // not the only time to quote, but whatever
            printf("%s", o.data.s);
        else
            printf("\"%s\"", o.data.s);
    }
    else if (o.type == obj::INT) {
        printf("%d", o.data.i);
    }
    else if (o.type == obj::DECIMAL) {
        printf("%s", o.data.s);
    }
    else if (o.type == obj::DATE) {
        printf("%s", o.data.s);
    }
    else if (o.type == obj::TITLE) {
        printf("%s", o.data.s);
    }
    else if (o.type == obj::BLOCK) {
        printf("{\n");
        print_block(indent+4, o.data.p_block);
        printf("%*s}", indent, "");
    }
    else if (o.type == obj::LIST) {
        printf("{ ");

        for (auto&& i : o.data.p_list->obj_list) {
            print_obj(indent, i);
            printf(" ");
        }

        printf("}");
    }
    else if (o.type == obj::COLOR) {
        printf("{ %u %u %u }", o.data.color.r, o.data.color.g, o.data.color.b);
    }
    else {
        assert(false);
    }
}



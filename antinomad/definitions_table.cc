

#include "definitions_table.h"
#include "error.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>


definitions_table::definitions_table(const default_map& dm) {

    const fs::path fsp{ dm.root_path() / "map" / dm.definitions_path() };
    const char* path = fsp.c_str();
    FILE* f;

    if ( (f = fopen(path, "rb")) == nullptr )
        throw va_error("could not open file: %s: %s", strerror(errno), path);

    char buf[256];
    uint n_line = 0;

    if ( fgets(&buf[0], sizeof(buf), f) == nullptr ) // consume CSV header
        throw va_error("definitions file lacks at least 1 line of text: %s", path);

    ++n_line;

    while ( fgets(&buf[0], sizeof(buf), f) != nullptr ) {

        ++n_line;

        char* p = &buf[0];

        if (*p == '#')
            continue;

        const uint N_COLS = 5;
        char* n_str[N_COLS];

        for (uint x = 0; x < N_COLS; ++x) {
            if ( (n_str[x] = strsep(&p, ";")) == nullptr)
                throw va_error("not enough columns on line %u: %s",
                               n_line, path);
        }

        const uint N_INT_COLS = N_COLS - 1;
        uint n[N_INT_COLS];
        p = 0;

        for (uint x = 0; x < N_INT_COLS; ++x) {
            n[x] = strtol(n_str[x], &p, 10);
            assert( *p == '\0' ); // there were no trailing non-numeric characters
        }

        if (n[0] != n_line-1)
            throw va_error("unexpected province ID %u on line %u: %s",
                           n[0], n_line, path);

        row_vec.emplace_back(n_str[4], n[1], n[2], n[3]);

        if (n[0] == dm.max_province_id())
            break;
    }

    fclose(f);

    if (row_vec.size() != dm.max_province_id())
        throw va_error("%u provinces defined for a map with %u: %s",
                       row_vec.size(), dm.max_province_id(), path);
}


void definitions_table::write(const fs::path& fspath) {

    const char* path = fspath.c_str();
    FILE* f;

    if ( (f = fopen(path, "wb")) == nullptr )
        throw va_error("could not write to file: %s: %s",
                       strerror(errno), path);

    fprintf(f, "province;red;green;blue;x;x\n");

    uint id = 0;

    for (auto&& r : row_vec)
        fprintf(f, "%u;%hhu;%hhu;%hhu;%s;x\n",
                ++id, r.red, r.green, r.blue, r.name.c_str());

    fclose(f);
}

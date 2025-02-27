// -*- c++ -*-

#ifndef _MDH_AN_PROVINCE_H_
#define _MDH_AN_PROVINCE_H_

#include <cstdio>
#include <vector>
#include <string>


class an_province {
public:

    struct hist_entry {
        uint year;
        std::string culture;
        std::string religion;
        bool has_temple;

        hist_entry(uint y, const char* cul, const char* rel, bool is_holy)
            : year(y), culture(cul), religion(rel), has_temple(is_holy) {}

        const char* holding_type() const noexcept {
            return (has_temple) ? "temple" : "tribal";
        }
    };

    typedef std::vector<hist_entry> hist_list_t;

private:

    uint _id;
    std::string _name;
    hist_list_t _hist_list;

public:

    an_province(uint id, const std::string& name) noexcept
        : _id(id), _name(name) {}

    uint id() const noexcept { return _id; }
    const std::string& name() const noexcept { return _name; }
    hist_list_t& hist_list() noexcept { return _hist_list; }
    const hist_list_t& hist_list() const noexcept { return _hist_list; }

    void write_event(FILE*, uint event_id) const;
};


#endif

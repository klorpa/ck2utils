#ifndef __LIBCK2_CSV_READER_H__
#define __LIBCK2_CSV_READER_H__

#include "common.h"


_CK2_NAMESPACE_BEGIN;


// appropriately, this code assumes CK2-style CSV files. that is, semicolon-separated, and quoting of fields is not
// a thing.


template<class TupleT, class RecordCallbackT, const char Delim = ';'>
class CSVReader {
    // TODO: implementation is worth 3 cookies!
};


_CK2_NAMESPACE_END;
#endif

# Change to any other value during local development
ENVIRONMENT = 'production'

# Collection with prepared data for experiments
PREPARED_COL_ID = 'prepared'


class CodeTypes:
    FAST_SSC = 'fast-ssc'
    RC_SCAN = 'rc_scan'
    ALL = [FAST_SSC, RC_SCAN]

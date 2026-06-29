import sys
import logging


handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(name)s, %(funcName)s, %(asctime)s, %(levelname)s - %(message)s.'
)
handler.setFormatter(formatter)

NEEDFUL = [
    'SECID', 'SHORTNAME', 'PREVPRICE', 'PREVWAPRICE', 'PREVDATE',
    'WAPTOPREVWAPRICE', 'UPDATETIME', 'LCURRENTPRICE', 'LAST',
    'PRICEMINUSPREVWAPRICE', 'DATAUPDATE', 'CURRENCYID', 'TRADINGSESSION',
    'LASTCHANGEPRCNT', 'WAPRICE', 'LASTCNGTOLASTWAPRICE', 'INSTRID', 'BOARDID',
    'WAPTOPREVWAPRICEPRCNT', 'MARKETPRICE', 'ISSUECAPITALIZATION',
    'TRENDISSUECAPITALIZATION', 'BOARDID', 'LOTSIZE', 'HIGH', 'LOW', 'SECTOR'
]

SHARE_GROUPS = ['TQBR']

STOP_TRADING = 'торги приостановлены'
RUN_TRADING = 'торги идут'

IMOEX_URL = (
    'http://iss.moex.com/iss/engines/stock/markets/shares/securities.json'
    '?iss.json=extended&iss.meta=off'
)

WPTPWP_POINTS = 5
LCP_POINTS = 5
PMPWP_WP_POINTS = 8
LCTLWP_WP_POINTS = 5
LCPRCNT_POINTS = 10
LMP_POINTS = 10
TIC_IC_POINTS = 7

MAX_SCORE = (
    WPTPWP_POINTS + LCP_POINTS + PMPWP_WP_POINTS +
    LCTLWP_WP_POINTS + LCPRCNT_POINTS + LMP_POINTS + TIC_IC_POINTS
)

STATUS_UP = 'вероятность роста'
STATUS_DOWN = 'вероятность падения'
STATUS_MEDIUM = 'среднее значение'

MIN = [-25, 10]
MAX = [5, 15]
MED = [-5, 5]

logger = logging.getLogger(name=__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
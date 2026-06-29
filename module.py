import json
import requests
import ast
from datetime import datetime
import pytz

from pyvis.network import Network

from settings import (
    logger,
    STOP_TRADING,
    SHARE_GROUPS,
    NEEDFUL,
    RUN_TRADING,
    IMOEX_URL,
    WPTPWP_POINTS,
    LCP_POINTS,
    PMPWP_WP_POINTS,
    LCTLWP_WP_POINTS,
    LCPRCNT_POINTS,
    LMP_POINTS,
    TIC_IC_POINTS,
    MAX_SCORE,
    STATUS_UP,
    STATUS_DOWN,
    STATUS_MEDIUM,
)


class DataProcessor:
    @classmethod
    def fetch_and_prepare_data(cls, is_offline=False):
        if is_offline:
            with open('data/work_time_data.txt', 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = requests.get(IMOEX_URL).json()

        securities = []
        marketdata = []
        for type_data in ['securities', 'marketdata']:
            for element in data[1][type_data]:
                new_dict = {}
                if type_data == 'securities':
                    new_dict['SHORTNAME'] = element.get('SHORTNAME')
                for key, value in element.items():
                    if key in NEEDFUL:
                        new_dict[key] = value
                if type_data == 'securities':
                    securities.append(new_dict)
                else:
                    marketdata.append(new_dict)

        return cls._merge_and_filter(securities, marketdata)

    @classmethod
    def _merge_and_filter(cls, securities, marketdata):
        result = []
        sector_dict = ast.literal_eval(open('data/secid_sector.txt', 'r').read())
        seen = set()

        for sec in securities:
            for md in marketdata:
                if sec['SECID'] == md['SECID']:
                    sec.update(md)

            sec['TRADINGSESSION'] = RUN_TRADING if str(sec.get('TRADINGSESSION')) == '1' else STOP_TRADING
            sector = sector_dict.get(sec['SECID'])
            if not sector:
                continue
            sec['SECTOR'] = sector
            sec['DATAUPDATE'] = datetime.now(pytz.timezone('Europe/Moscow')).strftime('%H:%M:%S (%d.%m)')

            if sec.get('CURRENCYID') == 'SUR':
                sec['CURRENCYID'] = 'рубль'
            if sec.get('INSTRID') != 'EQIN' or sec.get('BOARDID') not in SHARE_GROUPS:
                continue

            secid = sec.get('SECID')
            if secid and secid not in seen:
                seen.add(secid)
                result.append(sec)

        return result

    @staticmethod
    def format_capitalization_report(rows):
        total_cap = sum(r['issue_capitalization'] for r in rows)

        lines = ["\n--- Соотношение капитализаций по секторам ---"]
        for r in rows:
            lines.append(
                f"  {r['sector']:15} | {r['issue_capitalization']:.2f} "
                f"({(100 * r['issue_capitalization'] / total_cap):.2f} %)"
            )

        lines.append("\n--- Изменение капитализации по секторам ---")
        for r in rows:
            lines.append(
                f"  {r['sector']:15} | "
                f"{(100 * r['trendissue_capitalization'] / r['issue_capitalization']):.2f} %"
            )
        return "\n".join(lines)

    @classmethod
    def calculate_all_probabilities(cls, data=None, is_offline=False):
        if data is None:
            data = cls.fetch_and_prepare_data(is_offline=is_offline)

        calculator = ProbabilityCalculator()
        results = []
        for share in data:
            probability, components = calculator.compute(share)
            share['PROBABILITY'] = round(probability, 2)
            share['STATUS'] = calculator.get_status(probability)[0]
            share['STRENGTH'] = calculator.get_status(probability)[1]
            results.append({'share': share, 'probability': probability, 'components': components})

        results.sort(key=lambda x: x['probability'], reverse=True)
        return results

    @classmethod
    def print_probability_report(cls, data=None, is_offline=False, top_n=5):
        if data is None:
            data = cls.fetch_and_prepare_data(is_offline=is_offline)
        return ProbabilityCalculator().print_report(data, top_n)

    @staticmethod
    def build_probability_graph(sectors_data, output_file="results/probability_graph.html"):
        net = Network(
            height="700px", width="100%", directed=False, bgcolor="#101022",
            font_color="white", notebook=False, cdn_resources="in_line"
        )

        for sector, stocks in sectors_data.items():
            net.add_node(sector, label=sector, color="#4A90D9", size=40, shape="dot")
            for s in stocks:
                secid = s["secid"]
                prob = s["prob"]
                if prob >= 30:
                    color = "#2ECC71"
                elif prob <= -30:
                    color = "#E74C3C"
                else:
                    color = "#F1C40F"

                net.add_node(
                    secid,
                    label=secid,
                    title=f"{secid}: {prob}%",
                    color=color,
                    size=10,
                    shape="dot"
                )
                net.add_edge(sector, secid)

        html = net.generate_html()
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"Сохранено: {output_file} | Узлов: {len(net.nodes)}, Рёбер: {len(net.edges)}")
        return net


class ProbabilityCalculator:
    WEIGHTS = {
        'WAPTOPREVWAPRICEPRCNT': WPTPWP_POINTS,
        'LCURRENTPRICE': LCP_POINTS,
        'PRICEMINUSPREVWAPRICE': PMPWP_WP_POINTS,
        'LASTCNGTOLASTWAPRICE': LCTLWP_WP_POINTS,
        'LASTCHANGEPRCNT': LCPRCNT_POINTS,
        'MARKETPRICE': LMP_POINTS,
        'TRENDISSUECAPITALIZATION': TIC_IC_POINTS,
    }

    def _to_float(self, value):
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _calc_waptoprev(self, data):
        val = self._to_float(data.get('WAPTOPREVWAPRICEPRCNT'))
        return max(-1, min(1, val / 15))

    def _calc_price_position(self, data):
        last = self._to_float(data.get('LAST'))
        high = self._to_float(data.get('HIGH'))
        low = self._to_float(data.get('LOW'))
        if high == low or high == 0:
            return 0
        return ((last - low) / (high - low) - 0.5) * 2

    def _calc_price_deviation(self, data):
        val = self._to_float(data.get('PRICEMINUSPREVWAPRICE'))
        prev_wap = self._to_float(data.get('PREVWAPRICE'))
        if prev_wap == 0:
            return 0
        return max(-1, min(1, (val / prev_wap * 100) / 10))

    def _calc_momentum(self, data):
        val = self._to_float(data.get('LASTCNGTOLASTWAPRICE'))
        wap = self._to_float(data.get('WAPRICE'))
        if wap == 0:
            return 0
        return max(-1, min(1, (val / wap * 100) / 10))

    def _calc_last_change(self, data):
        val = self._to_float(data.get('LASTCHANGEPRCNT'))
        return max(-1, min(1, val / 10))

    def _calc_market_price(self, data):
        market = self._to_float(data.get('MARKETPRICE'))
        prev = self._to_float(data.get('PREVPRICE'))
        if prev == 0:
            return 0
        return max(-1, min(1, ((market - prev) / prev * 100) / 10))

    def _calc_cap_trend(self, data):
        trend = self._to_float(data.get('TRENDISSUECAPITALIZATION'))
        issue_cap = self._to_float(data.get('ISSUECAPITALIZATION'))
        if issue_cap == 0:
            return 0
        return max(-1, min(1, (trend / issue_cap * 100) / 5))

    def compute(self, data):
        components = {
            'WAPTOPREVWAPRICEPRCNT': self._calc_waptoprev(data),
            'LCURRENTPRICE': self._calc_price_position(data),
            'PRICEMINUSPREVWAPRICE': self._calc_price_deviation(data),
            'LASTCNGTOLASTWAPRICE': self._calc_momentum(data),
            'LASTCHANGEPRCNT': self._calc_last_change(data),
            'MARKETPRICE': self._calc_market_price(data),
            'TRENDISSUECAPITALIZATION': self._calc_cap_trend(data),
        }
        weighted_sum = sum(components[p] * w for p, w in self.WEIGHTS.items())
        probability = (weighted_sum / MAX_SCORE) * 100
        return max(-100, min(100, probability)), components

    def get_status(self, probability):
        if probability >= 30:
            return STATUS_UP, 'рост'
        elif probability > -10:
            return STATUS_MEDIUM, 'нейтрально'
        return STATUS_DOWN, 'падение'

    def print_report(self, data_list, top_n=5):
        output = ''
        results = []
        for data in data_list:
            probability, _ = self.compute(data)
            results.append({'data': data, 'probability': probability})

        results.sort(key=lambda x: x['probability'], reverse=True)

        output += "\n\n\nПовышенный рост:\n"
        growth = [r for r in results if r['probability'] > 0][:top_n]
        for i, r in enumerate(growth, 1):
            d = r['data']
            prob = r['probability']
            status, strength = self.get_status(prob)
            output += f"\n {i}. {d.get('SHORTNAME', 'N/A')} ({d.get('SECID', 'N/A')})\n"
            output += f"    Сектор: {d.get('SECTOR', 'Unknown')}\n"
            output += f"    Вероятность: +{prob:.1f} %  → {status} ({strength})\n"
            output += (f"    Цена за акцию: {self._to_float(d.get('LAST')):.2f} | "
                  f"Изменение: {self._to_float(d.get('LASTCHANGEPRCNT')):+.2f}%\n")
            output += f"    Капитализация: {self._to_float(d.get('ISSUECAPITALIZATION')):.2f} рублей\n"

        output += "\nПовышенное падение:\n"
        decline = [r for r in results if r['probability'] < 0][-top_n:]
        decline.reverse()
        for i, r in enumerate(decline, 1):
            d = r['data']
            prob = r['probability']
            status, strength = self.get_status(prob)
            output += f"\n {i}. {d.get('SHORTNAME', 'N/A')} ({d.get('SECID', 'N/A')})\n"
            output += f"    Сектор: {d.get('SECTOR', 'Unknown')}\n"
            output += f"    Вероятность: {prob:.1f} %  → {status} ({strength})\n"
            output += (f"    Цена за акцию: {self._to_float(d.get('LAST')):.2f} | "
                  f"Изменение: {self._to_float(d.get('LASTCHANGEPRCNT')):+.2f}%\n")
            output += f"    Капитализация: {self._to_float(d.get('ISSUECAPITALIZATION')):.2f} рублей\n"

        return output
""" Описание класса, для работы с БД."""

import requests
import json
from datetime import datetime
import pytz
import ast

from settings import (
    logger,
    STOP_TRADING,
    SHARE_GROUPS,
    TYPE_DATA_IMOEX,
    NEEDFUL,
    RUN_TRADING,
    IMOEX_URL
)


class GetAndPrepareData:
    """ Класс для работы с API imoex (iss)."""

    data = ''

    @classmethod
    def get_api_response(
        self,
        url,
        post=False,
        headers=None,
        body=None,
        delete=None
    ):
        """ Получение информации с запроса на сервер."""
        try:
            if post:
                return requests.post(url, headers=headers, json=body).json()
            elif delete:
                return requests.delete(url, headers=headers).json()
            return requests.get(url, headers=headers).json()
        except json.decoder.JSONDecodeError:     
            return requests.get(url, headers=headers)._content.decode('utf-8')

    @classmethod
    def data_prepare(self, is_offline=False):
        """ Фильтрация данных, полученных с запроса."""
        result = []
        data_list = []
        data = self.get_api_response(
            url=IMOEX_URL
        )
        if is_offline: data = json.load(open(
            file='work_time_data.txt',
            mode='r',
            encoding='utf-8'
        ))
        logger.info('get response info from ISS')
        # Фильтрация полученных данных (из разных "графов").
        for type_data in ['securities', 'marketdata']:
            for element in data[1][type_data]:
                new_dict = {}
                if type_data == 'securities':
                    new_dict['SHORTNAME'] = element.get('SHORTNAME')
                # Добавление только необходимых параметров из списка.
                key_list = []
                for key, value in element.items():
                    if key not in key_list:
                        key_list.append(key)
                    else:
                        continue
                    if key in NEEDFUL:
                        new_dict[key] = value
                # logger.info(f'key_list - {key_list}')
                data_list.append(new_dict)
            result.append(data_list)

        union_data = self.union_api_response(*result)
        # logger.info(union_data)
        return union_data


    @classmethod
    def union_api_response(self, data_sec, data_md):
        """ Добавляет доплнительные параметры и сводит всё в одну БД."""
        result = []
        sector_dict =  ast.literal_eval(open(
            'secid_sector.txt', 'r').read())
        for el_sec in data_sec:
            for el_md in data_md:
                # Сведение БД в одну.
                if el_sec['SECID'] == el_md['SECID']:
                    for key, val in el_md.items():
                        el_sec[key] = val
            # Добавление новых параметров.
            # logger.info(f"{el_md.get('TRADINGSESSION')}")
            # logger.info(f"{el_sec.get('TRADINGSESSION')}")
            if str(el_sec.get('TRADINGSESSION')) == '1':
                el_sec['TRADINGSESSION'] = RUN_TRADING
            else:
                el_sec['TRADINGSESSION'] = STOP_TRADING
            sector = sector_dict.get(el_sec['SECID'])
            if not sector: continue
            el_sec['SECTOR'] = sector

            format = '%H:%M:%S (%d.%m)'
            el_sec['DATAUPDATE'] = (
                datetime.now(pytz.timezone('Europe/Moscow'))
            ).strftime(format)
            # logger.info(el_sec)
            result.append(el_sec)
        # Проверка и вывод выходных данных.

        return self.sorted_data(result)


    @classmethod
    def sorted_data(cls, data):
        """Исправлено: безопасное удаление дубликатов"""
        seen = set()
        result = []
        
        for share in data:
            secid = share.get('SECID')
            if share['CURRENCYID'] == 'SUR':
                share['CURRENCYID'] = 'рубль'
            if (
                share.get('INSTRID') != 'EQIN'
            ):
                continue
            if share.get('BOARDID') not in SHARE_GROUPS:
                continue
            
            if secid and secid not in seen:
                seen.add(secid)
                result.append(share)
        return result

    @staticmethod
    def statistic_capitalization_message(trand_and_issuecapital):
        sum_issuecapital = 0
        sum_trandissuecapital = 0
        
        lines = ["=== Капитализация по секторам ===\n"]
        lines.append("--- Выпущенная капитализация ---")
        for row in trand_and_issuecapital:
            sum_issuecapital += row['issue_capitalization']
            sum_trandissuecapital += row['trendissue_capitalization']

        for row in trand_and_issuecapital:
            lines.append(
                f"  {row['sector']:15} | {row['issue_capitalization']} "
                f"({100 * (row['issue_capitalization'] / sum_issuecapital):.2f} %)"
            )
        
        lines.append("\n--- Торговая капитализация ---")
        for row in trand_and_issuecapital:
            lines.append(
                f"  {row['sector']:15} | {row['trendissue_capitalization']:>20,.0f} "
                f"({100 * (row['trendissue_capitalization'] / sum_trandissuecapital):.2f} %)"
            )
        
        lines.append("\n--- Соотношение по секторам ---")
        for row in trand_and_issuecapital:
            lines.append(f"  {row['sector']:15} | {(100 * row['trendissue_capitalization'] / row['issue_capitalization']):.2f} %")
        return "\n".join(lines)
    
    @classmethod
    def calculate_growth_probability(cls, data=None, is_offline=False):
        """
        Расчёт вероятности роста/падения для всех акций.
        Возвращает отсортированный список с вероятностями.
        """
        if data is None:
            data = cls.data_prepare(is_offline=is_offline)
        
        calculator = StockProbabilityCalculator()
        results = []
        
        for share in data:
            probability, components = calculator.calculate_probability(share)
            
            # Добавляем поля к записи
            share['PROBABILITY'] = round(probability, 2)
            share['STATUS'] = calculator.get_status(probability)[0]
            share['STRENGTH'] = calculator.get_status(probability)[1]
            
            results.append({
                'share': share,
                'probability': probability,
                'components': components
            })
        
        # Сортировка по вероятности убывания
        results.sort(key=lambda x: x['probability'], reverse=True)
        return results
    
    @classmethod
    def get_top_growth_shares(cls, n=10, is_offline=False):
        """Топ-N акций с наибольшей вероятностью роста"""
        all_results = cls.calculate_growth_probability(is_offline=is_offline)
        return [r for r in all_results if r['probability'] > 0][:n]
    
    @classmethod
    def get_top_decline_shares(cls, n=10, is_offline=False):
        """Топ-N акций с наибольшей вероятностью падения"""
        all_results = cls.calculate_growth_probability(is_offline=is_offline)
        decline = [r for r in all_results if r['probability'] < 0]
        decline.sort(key=lambda x: x['probability'])  # По возрастанию (самые отрицательные)
        return decline[:n]
    
    @classmethod
    def print_probability_report(cls, is_offline=False, top_n=10):
        """Печать полного отчёта по вероятностям"""
        calculator = StockProbabilityCalculator()
        data = cls.data_prepare(is_offline=is_offline)
        calculator.analyze_all(data, top_n=top_n)

    @classmethod
    def calculate_growth_probability(cls, data=None, is_offline=False):
        """Расчёт вероятности роста/падения для всех акций"""
        if data is None:
            data = cls.data_prepare(is_offline=is_offline)
        
        calculator = StockProbabilityCalculator()
        results = []
        
        for share in data:
            probability, components = calculator.calculate_probability(share)
            share['PROBABILITY'] = round(probability, 2)
            share['STATUS'] = calculator.get_status(probability)[0]
            share['STRENGTH'] = calculator.get_status(probability)[1]
            
            results.append({
                'share': share,
                'probability': probability,
                'components': components
            })
        
        results.sort(key=lambda x: x['probability'], reverse=True)
        return results
    
    @classmethod
    def print_top5_growth_report(cls, data=None, is_offline=False):
        """Печать ТОП-5 акций с наибольшей вероятностью роста"""
        if data is None:
            data = cls.data_prepare(is_offline=is_offline)
        
        calculator = StockProbabilityCalculator()
        return calculator.print_top5_growth(data)
    
    @classmethod
    def print_full_probability_report(cls, data=None, is_offline=False, top_n=5):
        """Полный отчёт по вероятностям"""
        if data is None:
            data = cls.data_prepare(is_offline=is_offline)
        
        calculator = StockProbabilityCalculator()
        return calculator.print_full_report(data, top_n=top_n)


class StockProbabilityCalculator:
    """
    Калькулятор вероятности роста/падения акций.
    Шкала: от -100 (вероятность падения) до +100 (вероятность роста)
    """
    
    # Коэффициенты весов для параметров (из settings.py)
    WEIGHTS = {
        'WAPTOPREVWAPRICEPRCNT': 5,    # WPTPWP_POINTS
        'LCURRENTPRICE': 5,            # LCP_POINTS
        'PRICEMINUSPREVWAPRICE': 8,    # PMPWP_WP_POINTS
        'LASTCNGTOLASTWAPRICE': 5,     # LCTLWP_WP_POINTS
        'LASTCHANGEPRCNT': 10,         # LCPRCNT_POINTS
        'MARKETPRICE': 10,              # LMP_POINTS
        'TRENDISSUECAPITALIZATION': 7,  # TIC_IC_POINTS
    }
    
    MAX_SCORE = sum(abs(v) for v in WEIGHTS.values())  # 50
    
    # Статусы из settings.py
    STATUS_UP = 'вероятность роста'
    STATUS_DOWN = 'вероятность падения'
    STATUS_MEDIUM = 'среднее значение'
    
    def __init__(self, sector_file='secid_sector.txt'):
        with open(sector_file, 'r') as f:
            self.sector_dict = ast.literal_eval(f.read())
    
    def _safe_float(self, value):
        """Безопасное преобразование в float"""
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    
    def calculate_wptpwp(self, data):
        """WAPTOPREVWAPRICEPRCNT: процент изменения средневзвешенной к предыдущей"""
        val = self._safe_float(data.get('WAPTOPREVWAPRICEPRCNT'))
        return max(-1, min(1, val / 15))
    
    def calculate_lcp(self, data):
        """LCURRENTPRICE: позиция в дневном диапазоне"""
        last = self._safe_float(data.get('LAST'))
        high = self._safe_float(data.get('HIGH'))
        low = self._safe_float(data.get('LOW'))
        if high == low or high == 0:
            return 0
        position = (last - low) / (high - low)
        return (position - 0.5) * 2
    
    def calculate_pmpwp(self, data):
        """PRICEMINUSPREVWAPRICE: отклонение от предыдущей средней"""
        val = self._safe_float(data.get('PRICEMINUSPREVWAPRICE'))
        prev_wap = self._safe_float(data.get('PREVWAPRICE'))
        if prev_wap == 0:
            return 0
        prcnt = (val / prev_wap) * 100
        return max(-1, min(1, prcnt / 10))
    
    def calculate_lctlwp(self, data):
        """LASTCNGTOLASTWAPRICE: импульс последней сделки"""
        val = self._safe_float(data.get('LASTCNGTOLASTWAPRICE'))
        wap = self._safe_float(data.get('WAPRICE'))
        if wap == 0:
            return 0
        prcnt = (val / wap) * 100
        return max(-1, min(1, prcnt / 10))
    
    def calculate_lcprcnt(self, data):
        """LASTCHANGEPRCNT: процент изменения последней цены"""
        val = self._safe_float(data.get('LASTCHANGEPRCNT'))
        return max(-1, min(1, val / 10))
    
    def calculate_lmp(self, data):
        """MARKETPRICE: рыночная цена относительно предыдущей"""
        market = self._safe_float(data.get('MARKETPRICE'))
        prev = self._safe_float(data.get('PREVPRICE'))
        if prev == 0:
            return 0
        prcnt = ((market - prev) / prev) * 100
        return max(-1, min(1, prcnt / 10))
    
    def calculate_tic_ic(self, data):
        """TRENDISSUECAPITALIZATION: динамика капитализации"""
        trend = self._safe_float(data.get('TRENDISSUECAPITALIZATION'))
        issue_cap = self._safe_float(data.get('ISSUECAPITALIZATION'))
        if issue_cap == 0:
            return 0
        prcnt = (trend / issue_cap) * 100
        return max(-1, min(1, prcnt / 5))
    
    def calculate_probability(self, data):
        """Расчёт вероятности роста/падения. Возвращает -100..+100"""
        components = {
            'WAPTOPREVWAPRICEPRCNT': self.calculate_wptpwp(data),
            'LCURRENTPRICE': self.calculate_lcp(data),
            'PRICEMINUSPREVWAPRICE': self.calculate_pmpwp(data),
            'LASTCNGTOLASTWAPRICE': self.calculate_lctlwp(data),
            'LASTCHANGEPRCNT': self.calculate_lcprcnt(data),
            'MARKETPRICE': self.calculate_lmp(data),
            'TRENDISSUECAPITALIZATION': self.calculate_tic_ic(data),
        }
        
        weighted_sum = sum(
            components[param] * weight 
            for param, weight in self.WEIGHTS.items()
        )
        
        probability = (weighted_sum / self.MAX_SCORE) * 100
        return max(-100, min(100, probability)), components
    
    def get_status(self, probability):
        """Определение статуса"""
        if probability >= 30:
            return self.STATUS_UP, 'сильный рост'
        elif probability >= 10:
            return self.STATUS_UP, 'умеренный рост'
        elif probability > -10:
            return self.STATUS_MEDIUM, 'нейтрально'
        elif probability > -30:
            return self.STATUS_DOWN, 'умеренное падение'
        else:
            return self.STATUS_DOWN, 'сильное падение'
    
    def print_top5_growth(self, data_list):
        """
        Вывод топ-5 акций с наибольшей вероятностью РОСТА
        с указанием секторов
        """
        results = []
        
        for data in data_list:
            probability, components = self.calculate_probability(data)
            results.append({
                'secid': data.get('SECID', 'N/A'),
                'shortname': data.get('SHORTNAME', 'N/A'),
                'sector': data.get('SECTOR', 'Unknown'),
                'probability': probability,
                'last': self._safe_float(data.get('LAST')),
                'prevprice': self._safe_float(data.get('PREVPRICE')),
                'lastchangeprcnt': self._safe_float(data.get('LASTCHANGEPRCNT')),
                'components': components,
            })
        
        # Сортировка по убыванию вероятности
        results.sort(key=lambda x: x['probability'], reverse=True)
        
        # Топ-5 роста
        top5 = [r for r in results if r['probability'] > 0][:5]
        
        print("\n" + "="*80)
        print("  ТОП-5 АКЦИЙ С НАИБОЛЬШЕЙ ВЕРОЯТНОСТЬЮ РОСТА")
        print("="*80)
        
        for i, r in enumerate(top5, 1):
            status, strength = self.get_status(r['probability'])
            change = r['lastchangeprcnt']
            change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
            
            print(f"\n  {i}. {r['shortname']} ({r['secid']})")
            print(f"     Сектор: {r['sector']}")
            print(f"     Вероятность роста: +{r['probability']:.1f}/100  [{status} | {strength}]")
            print(f"     Текущая цена: {r['last']:.2f}  (изменение: {change_str})")
            print(f"     Предыдущая цена: {r['prevprice']:.2f}")
        
        print("\n" + "="*80)
        
        # Дополнительно: статистика по секторам среди топ-5
        sector_counts = {}
        for r in top5:
            sector = r['sector']
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        print("\n  Распределение по секторам в ТОП-5:")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            print(f"     • {sector}: {count} акц.")
        
        print("="*80)
        
        return top5
    
    def print_full_report(self, data_list, top_n=5):
        """Полный отчёт: топ роста, топ падения, статистика по секторам"""
        
        # Собираем все результаты
        results = []
        for data in data_list:
            probability, components = self.calculate_probability(data)
            results.append({
                'data': data,
                'probability': probability,
                'components': components,
            })
        
        results.sort(key=lambda x: x['probability'], reverse=True)
        
        # === ТОП-5 РОСТА ===
        print("\n" + "_"*80)
        print(" "*29 + "ТОП-5 РОСТА" + " "*36)
        print("_"*80)
        
        growth = [r for r in results if r['probability'] > 0][:top_n]
        
        for i, r in enumerate(growth, 1):
            d = r['data']
            prob = r['probability']
            status, strength = self.get_status(prob)
            
            print(f"\n {i}. {d.get('SHORTNAME', 'N/A')} ({d.get('SECID', 'N/A')})")
            print(f"    Сектор: {d.get('SECTOR', 'Unknown')}")
            print(f"    Вероятность: +{prob:.1f}/100  → {status} ({strength})")
            print(f"    Цена: {self._safe_float(d.get('LAST')):.2f} | "
                  f"Изменение: {self._safe_float(d.get('LASTCHANGEPRCNT')):+.2f}%")
            print(f"    Капитализация: {self._safe_float(d.get('ISSUECAPITALIZATION')):,.0f}")
        
        # === ТОП-5 ПАДЕНИЯ ===
        print("\n" + "_"*80)
        print(" "*29 + "ТОП-5 ПАДЕНИЯ" + " "*36)
        print("_"*80)
        
        decline = [r for r in results if r['probability'] < 0][-top_n:]
        decline.reverse()
        
        for i, r in enumerate(decline, 1):
            d = r['data']
            prob = r['probability']
            status, strength = self.get_status(prob)
            
            print(f"\n {i}. {d.get('SHORTNAME', 'N/A')} ({d.get('SECID', 'N/A')})")
            print(f"    Сектор: {d.get('SECTOR', 'Unknown')}")
            print(f"    Вероятность: {prob:.1f}/100  → {status} ({strength})")
            print(f"    Цена: {self._safe_float(d.get('LAST')):.2f} | "
                  f"Изменение: {self._safe_float(d.get('LASTCHANGEPRCNT')):+.2f}%")
            print(f"    Капитализация: {self._safe_float(d.get('ISSUECAPITALIZATION')):,.0f}")
        
        
        return results
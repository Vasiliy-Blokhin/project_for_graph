import ast
from time import sleep

from module import GetAndPrepareData as gapd
from neo4j_worker import NEO4J
from settings import logger, STOP_TRADING


if __name__ == '__main__':
    
    NEO4J.start_work()
    
    while True:
        try:
            # Подготавливаем данные
            NEO4J.clear_shares()
            data = gapd.data_prepare()
            if data[0]['TRADINGSESSION'] == STOP_TRADING:
                data = gapd.data_prepare(is_offline=True)
            
            share_param_list = []
            for share in data:
                node = share['SECID']
                for rel, val in share.items():
                    share_param_list.append((node, rel, val))
            
            for share_param in share_param_list:
                node, rel, val = share_param
                
                # Заполняем БД полученными данными
                NEO4J.execute_query(
                    """
                    MERGE (s:Share {secid: $node})
                    SET s[$rel] = $val,
                        s.updated_at = datetime()
                    RETURN s
                    """,
                    node=node,
                    rel=rel,
                    val=val,
                    database_="neo4j"
                )
            
            # Получение данных для статистики
            trand_and_issuecapital = NEO4J.execute_query("""
                MATCH (s:Share)
                WHERE s.ISSUECAPITALIZATION IS NOT NULL
                OR s.TRENDISSUECAPITALIZATION IS NOT NULL
                RETURN s.SECTOR AS sector,
                    sum(s.ISSUECAPITALIZATION) AS issue_capitalization,
                    sum(s.TRENDISSUECAPITALIZATION) AS trendissue_capitalization
                ORDER BY issue_capitalization DESC
            """)

            logger.info(gapd.statistic_capitalization_message(
                trand_and_issuecapital.records
            ))

            # Расчет вероятностей
            probabilities = gapd.calculate_growth_probability(data=data)
            
            # Обновление данных в БД
            for item in probabilities:
                share = item['share']
                NEO4J.execute_query(
                    """
                    MATCH (s:Share {secid: $secid})
                    SET s.PROBABILITY = $probability,
                        s.STATUS = $status,
                        s.STRENGTH = $strength,
                        s.updated_at = datetime()
                    RETURN s
                    """,
                    secid=share['SECID'],
                    probability=round(item['probability'], 2),
                    status=share['STATUS'],
                    strength=share['STRENGTH'],
                    database_="neo4j"
                )

            # Вывод результата в терминал
            gapd.print_full_probability_report(is_offline=True, top_n=5)
        except Exception as e:
            logger.error(e)
        finally:
            logger.info('data update')
            sleep(600)
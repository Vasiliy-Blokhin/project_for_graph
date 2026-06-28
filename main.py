from time import sleep

from module import DataProcessor as dp
from neo4j_worker import NEO4J
from settings import logger, STOP_TRADING


if __name__ == '__main__':
    NEO4J.start_work()

    while True:
        try:
            NEO4J.clear_shares()
            data = dp.fetch_and_prepare_data()
            if data[0]['TRADINGSESSION'] == STOP_TRADING:
                logger.info('Торги приостановлены, использются оффлайн данные')
                data = dp.fetch_and_prepare_data(is_offline=True)

            for share in data:
                node = share['SECID']
                for rel, val in share.items():
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

            stats = NEO4J.execute_query("""
                MATCH (s:Share)
                WHERE s.ISSUECAPITALIZATION IS NOT NULL
                   OR s.TRENDISSUECAPITALIZATION IS NOT NULL
                RETURN s.SECTOR AS sector,
                    sum(s.ISSUECAPITALIZATION) AS issue_capitalization,
                    sum(s.TRENDISSUECAPITALIZATION) AS trendissue_capitalization
                ORDER BY issue_capitalization DESC
            """)

            probabilities = dp.calculate_all_probabilities(data=data)
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

            result_data = '\n'
            result_data += dp.format_capitalization_report(stats.records)
            result_data += dp.print_probability_report(is_offline=True, top_n=5)
            open('results/output.txt', 'w', encoding='utf-8').write(result_data)
            logger.info('Статистика сохранена')
            logger.info(result_data)

            result = NEO4J.execute_query("""
                MATCH (s:Share)
                WHERE s.SECTOR IS NOT NULL AND s.PROBABILITY IS NOT NULL
                RETURN s.SECTOR AS sector,
                    collect({secid: s.secid, prob: s.PROBABILITY}) AS stocks
            """)
            logger.info('Данные обновлены с учетом расчетов')

            sectors_data = {row["sector"]: row["stocks"] for row in result.records}
            dp.build_probability_graph(sectors_data, "results/moex_probability_graph.html")

        except Exception as e:
            logger.error(e)
        finally:
            logger.info('Конец итерации')
            sleep(600)
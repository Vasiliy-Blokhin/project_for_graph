from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from neo4j_worker import NEO4J
LLM_BASE_URL = "https://buzzai.cc/v1"
LLM_API_KEY = "sk-iu2SOvwxxYGJMQxjjHmZYJ9EKLF98BMjo6ymXlH95Ggm8jDz"
LLM_MODEL = "gpt-5.4-mini"

llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    use_responses_api=True,
    temperature=0,
)

prompt = ChatPromptTemplate.from_template("Вопрос: {q}\nКонтекст: {ctx}")
chain = prompt | llm

class EqSharesProbability:
    shares_data = ''
    contexts = []
    questions = []
    
    def __init__(self, len_shares):
        self.len_shares = len_shares

    @staticmethod
    def request_to_agent(question, context):
        result = chain.invoke({"q": question, "ctx": context})
        return result.content[0]['text']

    def get_share_info(self):
        self.shares_data = NEO4J.execute_query(f"""
            MATCH (s:Share)
            WHERE s.LAST IS NOT NULL
            AND s.HIGH IS NOT NULL
            AND s.LOW IS NOT NULL
            AND s.PREVWAPRICE IS NOT NULL
            AND s.WAPRICE IS NOT NULL
            AND s.PREVPRICE IS NOT NULL
            AND s.MARKETPRICE IS NOT NULL
            AND s.ISSUECAPITALIZATION IS NOT NULL
            AND s.TRENDISSUECAPITALIZATION IS NOT NULL
            AND s.WAPTOPREVWAPRICEPRCNT IS NOT NULL
            AND s.PRICEMINUSPREVWAPRICE IS NOT NULL
            AND s.LASTCNGTOLASTWAPRICE IS NOT NULL
            AND s.LASTCHANGEPRCNT IS NOT NULL
            RETURN s.secid AS ticker,
                s.SHORTNAME AS name,
                s.SECTOR AS sector,
                s.LAST AS last_price,
                s.HIGH AS day_high,
                s.LOW AS day_low,
                s.PREVWAPRICE AS prev_wap,
                s.WAPRICE AS wap,
                s.PREVPRICE AS prev_price,
                s.MARKETPRICE AS market_price,
                s.ISSUECAPITALIZATION AS capitalization,
                s.TRENDISSUECAPITALIZATION AS cap_trend,
                s.WAPTOPREVWAPRICEPRCNT AS wap_change_pct,
                s.PRICEMINUSPREVWAPRICE AS price_minus_prev_wap,
                s.LASTCNGTOLASTWAPRICE AS last_cng_to_wap,
                s.LASTCHANGEPRCNT AS last_change_pct,
                s.PROBABILITY AS probability,
                s.STATUS AS status,
                s.STRENGTH AS strength,
                s.updated_at AS updated_at
            ORDER BY s.PROBABILITY DESC
            LIMIT {self.len_shares}
                """)

    def get_context(self):
        for r in self.shares_data.records:
            self.contexts.append(f"""
                    =========================
                    Акция: {r['ticker']};
                    Цена: {r['last_price']}
                    ________________________
                    Параметры:
                    PREVWAPRICE - {r['prev_wap']},
                    WAPRICE - {r['wap']},
                    PREVPRICE - {r['prev_price']},
                    MARKETPRICE - {r['market_price']},
                    ISSUECAPITALIZATION - {r['capitalization']},
                    TRENDISSUECAPITALIZATION - {r['cap_trend']},
                    WAPTOPREVWAPRICEPRCNT - {r['wap_change_pct']},
                    PRICEMINUSPREVWAPRICE - {r['price_minus_prev_wap']},
                    LASTCNGTOLASTWAPRICE - {r['last_cng_to_wap']},
                    LASTCHANGEPRCNT - {r['last_change_pct']}
                    =========================
            """)
    
    def get_question(self):
        for r in self.shares_data.records:
            self.questions.append(f"""
            ### РОЛЬ:
            Ты финансовый аналитик, твоя задача получить данные из \
            контекста и рассчитать вероятность падения или роста в диапозоне \
            от -100 до 100
            
            ### ИНСТРУКЦИЯ:
            1. Получить контекст.
            2. Определить параметры акции.
            3. Произвести оценку акций.
            4. Вернуть результат пользователю в виде числа от -100 до 100.

            ### СТРОГИЕ ОГРАНИЧЕНИЯ:
            1. ФОРМАТ ВЫВОДА: результат только в виде числа от -100 до 100, рассуждения \
            и другой текст НЕДОПУСТИМ!
            """)

    def get_result(self):
        result = '\n Результаты анализа:\n'
        for i, r in enumerate(self.shares_data.records):
            result += f"""
            =========================
            {i+1}. Акция - {r['ticker']}
            ИИ - {self.request_to_agent(self.questions[i], self.contexts[i])};
            Алгоритм - {r['probability']};
            =========================
            """
        return result


if __name__ == '__main__':
    NEO4J().start_work()
    mini_agent = EqSharesProbability(len_shares=5)
    mini_agent.get_share_info()
    mini_agent.get_context()
    mini_agent.get_question()
    print(mini_agent.get_result())
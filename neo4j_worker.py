import os, sys, glob, time, socket, subprocess, json, pathlib, urllib.request, stat

from neo4j import GraphDatabase
import shutil

from settings import logger


class NEO4J:
    driver = None
    _process = None  # для хранения процесса Neo4j (если запускаем не как службу)

    @classmethod
    def execute_query(cls, query, **kwargs):
        """Выполняет запрос через драйвер Neo4j"""
        # database_ передаём отдельно, остальное — как параметры запроса
        database = kwargs.pop('database_', 'neo4j')
        return cls.driver.execute_query(query, parameters_=kwargs, database_=database)
    
    @classmethod
    def start_work(cls):
        """Главный метод: устанавливает и запускает Neo4j + Java 17"""

        # 1. Установка/проверка Neo4j
        NEO4J_DIR = "neo4j-community-5.26.0"
        if not os.path.exists(NEO4J_DIR):
            cls._install_neo4j(NEO4J_DIR)
        else:
            logger.info("Neo4j уже установлен")

        # 2. Установка/поиск Java 17
        JAVA17 = cls._find_or_install_java()
        if not JAVA17:
            raise RuntimeError(
                "Java 17 не найдена и не удалось установить автоматически. "
                "Установите Java 17 вручную с https://adoptium.net/"
            )
        logger.info(f"Java 17: {JAVA17}")

        # 3. Настройка конфигурации
        cls._configure_neo4j(NEO4J_DIR)

        # 4. Запуск Neo4j
        cls._start_neo4j(NEO4J_DIR, JAVA17)

        # 5. Подключение драйвера
        cls._connect_driver()


    # ───────────────────────────────────────────────
    # Установка Neo4j
    # ───────────────────────────────────────────────
    @classmethod
    def _install_neo4j(cls, NEO4J_DIR):
        logger.info("Скачиваем Neo4j Community 5.26.0...")
        zip_file = "neo4j-community-5.26.0-windows.zip"
        neo4j_url = "https://dist.neo4j.org/neo4j-community-5.26.0-windows.zip"

        # Скачивание с прогрессом
        cls._download_file(neo4j_url, zip_file)

        logger.info("Распаковываем архив...")
        shutil.unpack_archive(zip_file, ".")

        # Переименовываем папку
        extracted = "neo4j-community-5.26.0-windows"
        if os.path.exists(extracted):
            os.rename(extracted, NEO4J_DIR)

        # Удаляем zip
        if os.path.exists(zip_file):
            os.remove(zip_file)

        logger.info("Neo4j установлен")

    # ───────────────────────────────────────────────
    # Поиск или установка Java 17
    # ───────────────────────────────────────────────
    @classmethod
    def _find_or_install_java(cls):
        """Ищет Java 17; если не находит — пытается установить автоматически"""
        
        java_home = cls._install_java_portable()
        if java_home:
            return java_home


    @classmethod
    def _install_java_portable(cls):
        """Скачивание portable JDK 17 (Eclipse Temurin)"""
        zip_file = "jdk-17-portable.zip"
        extract_dir = "jdk-17"
        
        try:
            if os.path.exists(extract_dir):
                logger.info(f"Найдена существующая папка {extract_dir}, проверяем...")
                subdirs = [d for d in os.listdir(extract_dir) 
                          if os.path.isdir(os.path.join(extract_dir, d))]
                for sub in subdirs:
                    candidate = os.path.join(os.path.abspath(extract_dir), sub)
                    if os.path.exists(os.path.join(candidate, "bin", "java.exe")):
                        logger.info(f"Используем существующий JDK: {candidate}")
                        return candidate
            
            logger.info("Скачиваем portable JDK 17 (Eclipse Temurin)...")

            jdk_url = (
                "https://github.com/adoptium/temurin17-binaries/releases/"
                "download/jdk-17.0.9%2B9.1/"
                "OpenJDK17U-jdk_x64_windows_hotspot_17.0.9_9.zip"
            )

            cls._download_file(jdk_url, zip_file)

            logger.info("Распаковываем JDK...")
            
            if os.path.exists(extract_dir):
                cls._safe_rmtree(extract_dir)
            
            shutil.unpack_archive(zip_file, extract_dir)

            subdirs = [d for d in os.listdir(extract_dir) 
                      if os.path.isdir(os.path.join(extract_dir, d))]
            if subdirs:
                java_home = os.path.join(os.path.abspath(extract_dir), subdirs[0])
            else:
                java_home = os.path.abspath(extract_dir)

            if os.path.exists(zip_file):
                os.remove(zip_file)
            
            logger.info(f"Portable JDK установлен: {java_home}")
            return java_home

        except Exception as e:
            logger.warning(f"Portable JDK установка не удалась: {e}")
            if os.path.exists(zip_file):
                try:
                    os.remove(zip_file)
                except Exception:
                    pass
            return None

    @staticmethod
    def _safe_rmtree(path):
        """Безопасное удаление директории с обработкой ошибок доступа"""
        def onerror(func, path, exc_info):
            if not os.access(path, os.W_OK):
                try:
                    os.chmod(path, stat.S_IWUSR)
                    func(path)
                    return
                except Exception:
                    pass
            logger.warning(f"Не удалось удалить {path}: {exc_info[1]}")

        try:
            shutil.rmtree(path, onerror=onerror)
        except Exception as e:
            logger.warning(f"Не удалось очистить {path}: {e}")
            try:
                new_name = path + "_old_" + str(int(time.time()))
                os.rename(path, new_name)
                logger.info(f"Переименована заблокированная папка: {new_name}")
            except Exception:
                pass

    # Конфигурация Neo4j
    @staticmethod
    def _configure_neo4j(NEO4J_DIR):
        """Отключает аутентификацию Neo4j"""
        conf = os.path.join(NEO4J_DIR, "conf", "neo4j.conf")
        if not os.path.exists(conf):
            logger.warning(f"neo4j.conf не найден: {conf}")
            return

        with open(conf, 'r', encoding='utf-8') as f:
            txt = f.read()

        txt = txt.replace(
            "#dbms.security.auth_enabled=false", 
            "dbms.security.auth_enabled=false"
        )
        txt = txt.replace(
            "dbms.security.auth_enabled=true", 
            "dbms.security.auth_enabled=false"
        )

        with open(conf, 'w', encoding='utf-8') as f:
            f.write(txt)

        logger.info("Аутентификация Neo4j отключена")

    # Запуск Neo4j
    @classmethod
    def _start_neo4j(cls, NEO4J_DIR, JAVA17):
        """Запускает Neo4j: сначала как службу, если не получится — как процесс"""
        neo4j_bin = os.path.join(NEO4J_DIR, "bin", "neo4j.bat")
        env = {**os.environ, "JAVA_HOME": JAVA17}
        
        logger.info("Запускаем Neo4j...")
        cls._process = subprocess.Popen(
            [neo4j_bin, "console"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )

        logger.info("Ожидаем запуск Neo4j (порт 7687)...")
        for i in range(120):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                result = sock.connect_ex(("127.0.0.1", 7687))
                if result == 0:
                    logger.info("Neo4j запущен и доступен")
                    return
            time.sleep(1)
            if i % 10 == 0:
                logger.info(f"  ждём... ({i}s)")

        raise TimeoutError("Neo4j не запустился в течение 120 секунд")

    # Подключение драйвера
    @classmethod
    def _connect_driver(cls):
        """Создаёт и проверяет подключение к Neo4j"""
        cls.driver = GraphDatabase.driver("bolt://localhost:7687")
        cls.driver.verify_connectivity()
        result = cls.driver.execute_query("RETURN 'Neo4j ' + '5.26' AS hello")
        logger.info(f"Подключено: {result.records[0]['hello']}")

    # Вспомогательные методы
    @staticmethod
    def _download_file(url, filepath):
        """Скачивает файл с отображением прогресса"""
        logger.info(f"Скачивание: {url}")

        def report_progress(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(downloaded * 100 / total_size, 100)
                if block_num % 20 == 0:
                    logger.info(f"  {percent:.1f}% ({downloaded//1024//1024}MB / {total_size//1024//1024}MB)")

        urllib.request.urlretrieve(url, filepath, reporthook=report_progress)
        logger.info(f"Скачано: {filepath}")

    @classmethod
    def stop_work(cls):
        """Останавливает Neo4j и закрывает драйвер"""
        if cls.driver:
            cls.driver.close()
            cls.driver = None
            logger.info("Драйвер Neo4j закрыт")

        if cls._process:
            cls._process.terminate()
            cls._process = None
            logger.info("Neo4j процесс остановлен")
        else:
            # Пробуем остановить службу
            try:
                neo4j_bin = os.path.join("neo4j-community-5.26.0", "bin", "neo4j.bat")
                subprocess.run([neo4j_bin, "stop"], check=False, timeout=30)
                logger.info("Neo4j служба остановлена")
            except Exception:
                pass

    @classmethod
    def clear_all(cls):
        cls.execute_query("MATCH (n) DETACH DELETE n", database_="neo4j")

    @classmethod
    def clear_shares(cls):
        cls.execute_query("MATCH (s:Share) DETACH DELETE s", database_="neo4j")

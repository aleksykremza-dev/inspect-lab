# Research: threat landscape catalog 2025–2026 (2026-10-06)

Source: research agent по промпту Alex (каталог принципов, без пейлоадов). VERIFIED = подтверждено первоисточником в сессии.
**Неполнота:** первая версия ответа агента была остановлена; в итоговом ответе есть строки #21–#45 и разделы 7, 8, A, B, C.
Строки #1–#20 (чат-боты: прямые инъекции, обходы фильтров, кодировки, многоходовые) в текст не попали — на них есть только ссылки
из раздела A (#1, #2, #3, #5, #6, #7, #8, #9, #12, #13, #15, #16, #17, #18, #19). Для базы атак S1 опираемся на опубликованные
наборы из раздела B (CyberSecEval variants — см. methodology.md §1.1, BIPIA, deepset, Gandalf).

---

## 3 (продолжение). Агенты с инструментами — классы без механики

| # | Класс | OWASP / ATLAS | Публичные случаи | Статус | Защита |
|---|---|---|---|---|---|
| 21 | Утечка данных через рендеринг вывода (ссылки/изображения/unfurling) | LLM02, LLM05 / T0057, T0067 | Slack AI — PromptArmor 2024-08 https://promptarmor.com/resources/data-exfiltration-from-slack-ai-via-indirect-prompt-injection ; ChatGPT url_safe bypass — Tenable TRA-2025-06 | P по продуктам; класс открыт | Не рендерить внешние URL; allowlist доменов; текст-only |
| 22 | Персистентность через память агента | LLM01 / T0051.002 | ChatGPT macOS «SpAIware» 2024-09; Gemini memory 2025-02 (Rehberger) | P | Запись в память только по явному действию; аудит |
| 23 | Инъекция → конфигурация IDE/агента → исполнение кода | LLM06 / T0053 | Copilot CVE-2025-53773; Cursor CurXecute CVE-2025-54135 | P | Конфиг вне зоны записи агента; подтверждение изменений |
| 24 | Утечка через allowlisted утилиты/рендереры | LLM02, LLM06 / T0057 | Claude Code CVE-2025-55284; Cursor Mermaid CVE-2025-54132 | P | Минимальный allowlist; egress-контроль |
| 25 | «Toxic agent flows»: публичный источник → приватные данные → публичный вывод | LLM06, LLM02 / T0053 | GitHub MCP — Invariant 2025-05-26 https://invariantlabs.ai/blog/mcp-github-vulnerability ; Supabase MCP 2025-07 | открыт (архитектурный) | Rule of Two (Meta 2025-10-31 https://ai.meta.com/blog/practical-ai-agent-security/ ); lethal trifecta (Willison 2025-06) |
| 26 | MCP tool poisoning / rug pull | LLM03, LLM01 / T0010, T0051.001 | Invariant WhatsApp MCP 2025-04; MCPoison CVE-2025-54136 (Check Point 2025-08) | открыт | Pin хэшей описаний инструментов; allowlist серверов |
| 27 | Агентные браузеры: инструкции в содержимом страниц | LLM01 / T0051.001 | Perplexity Comet — Brave 2025-08-20; OpenAI Atlas 2025-12-22 https://openai.com/index/hardening-atlas-against-prompt-injection («вряд ли будет полностью решено») | F | Отделение запроса от контента страницы; подтверждения; adversarial RL |
| 28 | Computer-use агент выполняет действия из веб-контента | LLM06 / T0053 | ZombAIs — Rehberger 2024-10 | F (демо) | Изоляция среды; запрет загрузки/запуска |
| 29 | ANSI escape-последовательности в выводе LLM/MCP | LLM05 / T0067 | Trail of Bits 2025-04-29 https://blog.trailofbits.com/2025/04/29/deceiving-users-with-ansi-terminal-codes-in-mcp/ | открыт | Экранирование непечатаемых символов |
| 30 | No-code агенты поддержки (Copilot Studio, Agentforce) | LLM01, LLM02, LLM06 | Zenity (CSA), Tenable (Copilot Studio leak), SalesBleed (Agentforce 2025) | P по кейсам; класс открыт | Проверка личности вне LLM; минимальные права; человек в контуре |
| 31 | Автоматически оптимизированные обфусцированные промпты | LLM01 / T0068, T0057 | Imprompter — arXiv 2410.14923 (Mistral LeChat ~80% ASR; исправлено) | P/O | Фильтр внешних ссылок на выходе; детекция нечитаемых строк |

## 4. RAG и ресурсы

| # | Класс | OWASP / ATLAS | Источник | Статус | Защита |
|---|---|---|---|---|---|
| 32 | **PoisonedRAG** — отравление базы знаний | LLM04, LLM08 / T0070, T0066 | Zou et al., USENIX Security 2025 https://www.usenix.org/conference/usenixsecurity25/presentation/zou ; 5 текстов на вопрос → ~90% ASR | F (black-box) | Контроль источников записи; подпись/происхождение документов; детекция «подогнанных» чанков |
| 33 | ConfusedPilot — confused deputy в корпоративном RAG | LLM04, LLM02 / T0070 | DEF CON AI Village 2024, arXiv 2408.04870 | F | ACL на уровне retrieval |
| 34 | Инверсия эмбеддингов | LLM08 / T0024.001 | vec2text, arXiv 2310.06816: 92% восстановления 32-токенных текстов | O/F | Доступ к векторам = доступ к тексту |
| 35 | OverThink — замедление reasoning-моделей | LLM10 / T0034.001 | arXiv 2502.02542: 18–46× токенов | F | Лимит reasoning-токенов |

## 5. Multi-agent и LLM-судьи

| # | Класс | OWASP / ATLAS | Источник | Статус | Защита |
|---|---|---|---|---|---|
| 36 | Prompt Infection — саморепликация между агентами | LLM01 / T0061 | arXiv 2410.07283 | O/F | LLM Tagging + instruction defense |
| 37 | MAS control-flow hijacking | LLM06 / T0053 | COLM 2025, arXiv 2503.12188: Magentic-One 88–97% | F | Проверка маршрутизации на уровне оркестратора |
| 38 | **Универсальные фразы, завышающие оценку судьи** | LLM01 / T0054 | Raina et al., EMNLP 2024 https://aclanthology.org/2024.emnlp-main.427 ; абсолютное скорирование уязвимее сравнительного | F | Сравнительная оценка; ансамбль; судья не видит сырой текст пользователя |
| 39 | JudgeDeceiver — инъекция в оцениваемый ответ | LLM01 | arXiv 2403.17710 (CCS 2024) | O/F | Детекция перплексии; отделение данных от инструкции судье |
| 40 | Атаки на groundedness/safety-судей | LLM01, LLM09 | AdvERSEM *SEM 2025; «Know Thy Judge» arXiv 2503.04474; «A Coin Flip for Safety» arXiv 2603.06594 (2026-03) | F | Adversarial-обучение судьи; метаоценка |

## 6. Системный промпт и инциденты ботов поддержки

| # | Случай | OWASP | Что пошло не так | Чем кончилось | Источник |
|---|---|---|---|---|---|
| 41 | Извлечение системного промпта (класс) | LLM07 / T0056 | Lakera Q4-2025: ~60% наблюдаемых атак — попытки извлечь инструкции | Промпты считаются публичными | Willison 2023-02 (Sydney); Lakera |
| 42 | **Air Canada** — выдуманная политика bereavement-тарифа | LLM09 | бот сообщил неверную процедуру возврата; компания назвала бота «отдельным юрлицом» | Moffatt v. Air Canada, 2024 BCCRT 149: duty of care, CAD 812 | https://decisions.civilresolutionbc.ca/crt/crtd/en/525448/1/document.do |
| 43 | **Chevrolet of Watsonville** — переопределение цели бота | LLM01 / T0051.000 | пользователь задал боту новую «цель»; бот «продал» Tahoe за $1 | сделку не признали; бота ограничили | https://incidentdatabase.ai/entities/chevrolet-of-watsonville |
| 44 | DPD — брань и критика компании | LLM01 | бот поддался на провокацию | AI-компонент отключён (2024-01) | https://incidentdatabase.ai/reports/3616 |
| 45 | Lenovo Lena — XSS через вывод бота | LLM05 | нет санитизации HTML в ответах | исправлено (2025-08) | https://www.csoonline.com/article/4043005/lenovo-chatbot-breach.html |

## 7. Threat intel (андеграунд через публичные отчёты)

- Trend Micro 2026-01-28: рынок консолидировался вокруг jailbreak-as-a-service поверх коммерческих API; WormGPT-клоны, Xanthorox ($300/мес). Атаки на ботов поддержки отдельно не описаны. https://www.trendmicro.com/vinfo/us/security/news/cybercrime-and-digital-threats/the-state-of-criminal-ai
- KELA 2025: +52% обсуждений джейлбрейков на форумах, +200% упоминаний вредоносных AI-инструментов.
- Check Point AI Security Report 2025: ролевые рамки, «гипотетика/исследование»; 1 из 80 корпоративных промптов — высокий риск утечки.
- Kaspersky 2024-08: indirect PI «в дикой природе» — в основном резюме с инструкциями для HR-скрининга; финансовых злоупотреблений не найдено.
- Anthropic Threat Intelligence 2025-08: «vibe hacking», вымогательская кампания против 17 организаций.

## 8. Защиты с измеренным эффектом

| Защита | Эффект | Источник |
|---|---|---|
| Constitutional Classifiers | 183 участника, >3000 ч, 0 универсальных джейлбрейков; +0.38% отказов | https://www.anthropic.com/research/constitutional-classifiers (2025-02) |
| Adversarial RL + классификаторы (Claude for Chrome) | ASR ~1% при BoN-100 | https://www.anthropic.com/research/prompt-injection-defenses (2025-11) |
| CaMeL | 77% задач AgentDojo с доказуемой безопасностью | arXiv 2503.18813 |
| 6 архитектурных паттернов | ограничение возможностей вместо фильтрации | arXiv 2506.08837 (2025-06) |
| Instruction hierarchy | +63% робастности | https://openai.com/index/the-instruction-hierarchy/ |
| Rule of Two / lethal trifecta | не совмещать недоверенный вход + приватные данные + внешнее действие | Meta 2025-10; Willison 2025-06 |
| Gray Swan IPI Arena | 13 моделей, 272k атак; ASR 0.5% (Opus 4.5) – 8.5% (Gemini 2.5 Pro); ни одна не чиста | https://www.grayswan.ai/blog/uk-aisi-x-gray-swan-agent-red-teaming-challenge-results-snapshot |

---

## A. Применимость к kremzapay-bot

| Компонент бота | Что применимо | Контроль, который стоит проверить/рекомендовать |
|---|---|---|
| Нет истории диалога | снимает многоходовые; **не снимает** сфабрикованный «диалог» в одном сообщении | лимит длины; классификатор видит весь вход |
| temperature=0 | воспроизводимость, не безопасность: перебор вариаций входа работает | rate-limit; детекция серий близких запросов |
| Regex-фильтр | обходится кодировками, Unicode, разрежением текста | нормализация NFKC + удаление невидимых символов **до** regex и LLM; regex — дешёвый первый слой, не защита |
| LLM-классификатор темы | переформулировка/обёртка меняет «тему»; адаптивный противник обойдёт | классифицировать нормализованный пересказ; fail-closed; adversarial eval классификатора (arXiv 2510.09023) |
| RAG по markdown | #32, #33: кто пишет в статьи — тот управляет ботом; HTML-комментарии, невидимые символы | контроль записи (ревью/подпись статей); стрип HTML-комментариев и невидимых символов при индексации; Spotlighting/datamarking чанков; boundary reminder (BIPIA) |
| LLM-судья обоснованности | #38–#40: фразы в ответе или в чанке завышают оценку; абсолютное скорирование уязвимее | судья получает только ответ + источники; парная оценка; ансамбль из 2 моделей; fail-closed |
| Вывод в UI | #21, #45: markdown-ссылки/картинки/HTML | текст-only или allowlist доменов; экранирование HTML |
| Содержание ответов | #42, #43: выдуманная политика, «согласие» с клиентом; Air Canada — ответственность на операторе | цитируемость каждого утверждения; запрет обещаний без источника; эскалация к человеку |
| Системный промпт | ~60% атак в поле — попытки извлечь | считать утёкшим; ничего секретного в промпте |
| Инструменты | нет → #20–#31 не применимы; любой tool с записью = Rule of Two и пересмотр модели угроз | — |

## B. Публичные датасеты для воспроизводимого eval

| Название | Размер | Лицензия | URL | Релевантность для нас |
|---|---|---|---|---|
| **BIPIA** | 5 задач, 30 text + 20 code attack types | MIT | https://github.com/microsoft/BIPIA | **S2** (отравленные документы, QA/Summarization) |
| **LLMail-Inject** (Microsoft) | 462K submissions, адаптивные атаки против Spotlighting | MIT | https://huggingface.co/datasets/microsoft/llmail-inject-challenge | S2: обходы маркировки чанков |
| **deepset/prompt-injections** | 662 (263 инъекции / 399 легитимных) | Apache-2.0 | https://huggingface.co/datasets/deepset/prompt-injections | **S1** + контроль (легитимные = готовые чистые) |
| **Lakera gandalf_ignore_instructions** | 1 000 | MIT | https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions | S1: прямые инъекции |
| CyberSecEval 2 prompt_injection | 12 variants, PL/EN-подобное поле `speaking_language` | MIT | PurpleLlama repo | S1: таксономия приёмов для метки `technique` |
| JailbreakBench JBB-Behaviors | 200 + 300 judge pairs | MIT | https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors | калибровка судьи (если понадобится) |
| HarmBench | 510 behaviors | MIT | https://github.com/centerforaisafety/HarmBench | вне рамок (harm, не injection) |
| WildJailbreak | 262K + 2 210 | ODC-BY, гейт | https://huggingface.co/datasets/allenai/wildjailbreak | вне рамок |
| AgentDojo / InjecAgent | 629 / 1 054 | MIT | см. methodology.md | агенты с инструментами — не наш случай, но образец схемы |
| PoisonedRAG | код + BEIR | MIT | https://github.com/sleeepeer/PoisonedRAG | S2: метод построения отравленных чанков |

## C. Статус проверки (обновлено по `merge_notes.md` §4, параллельная проверка Alex 2026-10-06)

| Пункт | Статус |
|---|---|
| BoN Jailbreaking, arXiv 2412.03556 (Hughes et al., 2024-12-04) | **подтверждено** |
| Crescendo, arXiv 2404.01833 (Russinovich, Salem, Eldan, 2024-04-02) | **подтверждено** |
| Spotlighting, arXiv 2403.14720 (Hines et al., 2024-03-20) | **подтверждено** |
| HackerOne-writeups OpenAI/Anthropic | приватны — факт, не пробел; одна строка в ограничениях |
| DEF CON 33 GRT-3, Gray Swan ART, Gandalf Agent Breaker | закрытые данные; цитируется вторично |
| Policy Puppetry, Echo Chamber | только вендорские заявления — «заявлено вендором», выводов не строить |
| Цифры системных карт OpenAI | вторичные — пометить |
| Kaspersky 2025 по ботам поддержки | не найдено — claim убран, остаётся Kaspersky 2024 (indirect PI в резюме) |
| Malicious-Educator лицензия | не используется — убрано |
| MITRE ATLAS IDs | из официального YAML `mitre-atlas/atlas-data` — первоисточник (сайт отдавал 404) |

# 確認⑤：初回モデル候補と正式観測用API方針（Aの採用を別記録に保存済み）

2026-11-01の所有者の明示回答に基づき、候補とAPI方針だけの採用を別記録に保存しました。
対象の元YAMLは変更せず、exact model/profileの最終ロックやアカウントでの確認完了とは
扱いません。現在は[確認⑥：費用・実行上限](BUDGET-LIMITS-06.md)へ進みます。
以下は確認時に提示した内容です。

2026-11-01。直前の「A（3か月間隔・目標18時間／上限24時間）を採用しますか？」への
所有者の「はい」を、この方針だけの採用として別記録へ転記しました。
対象は[頻度・時間枠案v0.1](cadence-window-04.proposal.yaml)の正確なハッシュです。
[進行状況](decision-progress.yaml)は⑤へ進み、具体的な日時・費用・実行許可・モデル選定の
承認には拡張していません。旧提案ファイル、凍結文書、過去の観測は変更しません。

## A（推奨）：初回はW0の4候補とAPI条件を継承し、実行前に別途固定する

| 永久series | 初回の候補ID | 第一当事者API | 観測環境 |
|---|---|---|---|
| M01 OpenAI | `gpt-5.6-sol` | Responses | CLOSED |
| M02 Anthropic | `claude-opus-5` | Messages | CLOSED |
| M03 Google | `gemini-3.6-flash` | generateContent（直接REST） | CLOSED |
| M05 Perplexity | `perplexity/sonar` | Agent API `/v1/agent` | NATIVE・別集計 |

初回のW0とのつながりを優先する候補であり、現在の最新モデルや最高性能の比較ではありません。
公開資料ではClaude Opus 5はactive legacy、Gemini 3.6 Flashは旧世代として掲載されています。
資料に載っているだけでは、ご本人のアカウントでの利用可否や実行時の同一性を確認したことには
なりません。利用不可・返却ID不一致なら、別モデルや別ルーターへ自動で替えずに止めます。

永久lineage `MIBO-SL-002 — Claude` は変更せず、Opusというtierを永久ID名にしません。
Anthropicは現代のcanonical model IDをpinnedな版として説明していますが、serving環境等に
よる行動の変動まで排除するものとは扱いません。他社を含め、行動の不変性は保証しません。

初回の候補は、全将来Waveに対する永久・年間model lockでもありません。各Wave前に
第一当事者の情報と利用可否を改めて確認し、人間が正確な候補を決めてruntime model lockへ
固定します。後継モデルや別familyへ自動更新しません。exact IDはscientific manifestへ
後から埋める値ではなく、各Waveで別にロックする運用値です。

## 共通条件と、8192の意味

Frozen原文だけの独立したuser 1ターン・非ストリーミングを維持します。研究者が加える
system/developer/言語・役割指示、履歴、前の応答へのリンク、files/RAG/memory、CLOSEDの
tools/searchは使いません。任意のsamplingやreasoning/thinking/effortの指定も省略します。
SDKによる自動の継続生成やモデル切替を使わず、実際の送信JSONを検査・保存します。

上限設定はM01 `max_output_tokens`、M02 `max_tokens`、M03 `generationConfig.maxOutputTokens`、
M05 `max_output_tokens` の8192を候補とします。これは表示文を8192 tokensまで必ず出せる
保証ではありません。特にClaudeではthinkingもこの予算に含まれます。W0で打切りがなかった
少数例から、70項目すべてで影響がないとは推測しません。stop理由・使用量・公開された
thinking/content metadata等を残し、打切りや拒否、短答・質を理由に再送信・差替えしません。
provider自身が制御する内部指示や処理経路を、研究者側から完全に観測できるとも主張しません。

## Perplexityは新計画専用の正式profile候補として明示的に採用する案

W0-onlyのprofileを正式観測用へ改名して流用するのではなく、新しい用途・版・ハッシュの
profileを別途作り、承認・検証してからロックする方針です。指定するのはPerplexity自身の
Agent APIとcatalog ID `perplexity/sonar` で、使えるtoolは `web_search` だけとします。
ただし検索の実行自体を追加指示で強制せず、使うかどうかも観測として記録します。

`models` fallback list、effort preset、saved profile、instructions、language preference、
history・files・skillsや他のtoolsは省略します。旧Sonarへのfallbackや `disable_search` は
使いません。旧APIとの行動同等性、公式CLOSED適格性、consumer UIとの同等性を主張せず、
旧W01の科学的Manifestも変更しません。追加のno-search診断は今回提案しません。

## B：候補やAPI条件を見直してから決める

旧世代ではなく後継候補を検討したい等の場合は、具体的な希望を確認して、第一当事者資料に
基づく新しい案を作ります。Bでも勝手に最新へ置換したり、xAIを追加したりはしません。

## 公開資料と、まだ通過していないgate

公開資料の確認にOpenAI Docsを使用しました。今回のモデル選定・API方針の文書確認では、
API接続コードやcredential設定を変更せず、キーのpresence確認・読込み・再利用・新規作成も
行いません。authenticated Models API GETや生成への許可は含まれていません。

- [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol): candidate and Responses support; optional effort is omitted, not fixed to the documented default.
- [Claude Opus 5 overview](https://platform.claude.com/docs/en/models/opus-5/overview), [model-ID semantics](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions), [thinking budget](https://platform.claude.com/docs/en/build-with-claude/context-windows): legacy listing, canonical snapshot semantics, and shared thinking/output budget.
- [Gemini 3.6 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash), [generateContent reference](https://ai.google.dev/api/generate-content): previous-generation listing, REST method and returned `modelVersion`.
- [Perplexity catalog](https://docs.perplexity.ai/docs/agent-api/models), [Agent API](https://docs.perplexity.ai/api-reference/agent-post), [Web Search](https://docs.perplexity.ai/docs/agent-api/tools/web-search): exact Sonar catalog name, single-model selection, output field and optional search tool. No fallback list or effort preset is adopted.

アカウント権限、現在のexact metadata、quota、各社700件を時間枠内に実行する能力、
正式profileのpayload監査・試験・ハッシュ、最終model lock、利用条件・ガバナンス等は
未完了です。この選択は候補と方針だけで、scientific freezeや観測開始の許可ではありません。

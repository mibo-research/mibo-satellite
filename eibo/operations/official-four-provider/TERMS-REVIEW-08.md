# 確認⑧：利用条件・原記録保存・公表の方針（未承認案）

2026-11-01。所有者の明示回答「A。私が単独のプロトコル・運用責任者を担う方針を採用します。
完成版の最終承認も私とし、次の利用条件レビューを推奨選択肢付きで進めてください。」を、
[責任者方針v0.1](protocol-owner-07.proposal.yaml)の正確なハッシュへ結びつけて別記録に保存しました。
ご本人を単独の責任者・最終承認者とする方針だけであり、完成版への最終承認、所属機関の
承認、利用条件・倫理判断、日時や実行許可は推測しません。[現在の進行](decision-progress.yaml)は⑧です。

## 公開資料の予備レビュー

これは法律意見や契約上の適法性の確定ではありません。OpenAI DocsでAPIのデータ取扱いを、
その公式文書から案内される契約・公表方針、および他3社の第一当事者規約を確認しました。
各アカウントで締結した契約・注文書、現在の有料/無償設定、組織代理権は未確認です。
表の「要確認」は許可・違反のどちらも断定していません。公開ページの取得日は、その人や
予定観測日に適用される契約の発効日とは異なります。ページ原本のbyte hashを取得済みとも扱いません。

| 会社 | 確認した点 | 正式開始前に残る確認 |
|---|---|---|
| OpenAI | [公表方針のResearch節](https://openai.com/policies/sharing-publication-policy/)はAPI研究公表を歓迎。 | 実際の契約、AUP適用範囲、保存・公表・表示条件の人間判断。 |
| Anthropic | [Commercial Terms B/D](https://www.anthropic.com/legal/commercial-terms)は出力の権利と利用上の制約を規定。 | 現行AUPの版、適用契約・opt-in/model別条件と研究範囲。 |
| Google | [Gemini追加規約](https://ai.google.dev/gemini-api/terms?hl=en)は有料/無償でデータ利用を区別。 | 有料projectの確認、[一般API規約5(e)/8(b)](https://developers.google.com/terms)と生成物の保存・再配布の関係。 |
| Perplexity | [API規約2.1/2.3/2.5/5](https://www.perplexity.ai/en-GB/hub/legal/perplexity-api-terms-of-service)と[AUP](https://www.perplexity.ai/en-GB/hub/legal/aup)に利用範囲・保護対象・制約。 | Agent APIへの契約適用、長期保存・coding用export・比較公表・検索由来内容の権利。 |

OpenAIでは[Services Agreement 3.3/4/10](https://openai.com/policies/services-agreement/)と
[API Service Terms](https://openai.com/policies/service-terms/)も確認対象です。出力の権利が
利用者にある旨だけで、あらゆる第三者権利・引用・商標や公表を許可済みとは判断しません。
[APIデータ資料](https://developers.openai.com/api/docs/guides/your-data)のabuse monitoring等は、
研究者側の独立1ターンとは別です。store=falseをprovider側の保存ゼロとは解釈しません。

Anthropicは[Service Specific Terms E/F/G](https://www.anthropic.com/legal/service-specific-terms)
も確認対象です。今回取得された[AUPページ](https://www.anthropic.com/legal/aup)は韓国語で、
発効日2026-11-12の表示でした。確認日11-01の現行版とみなさず、適用する版の確認を残します。
OpenAIの[最新Usage Policies](https://openai.com/policies/usage-policies/)も11-20発効表示です。
明示リンクから[2025-10-29版](https://openai.com/policies/usage-policies/revisions/2025-10-29/)も
取得し、将来版と区別しました。実際の観測日時が決まったら適用版を再確認します。

Googleの[Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy)と
Perplexity AUPは研究等の例外に言及しますが、自動的な免除とはしません。Frozen全70項目を
読み、追加の人間AUP確認の例としてE2-02、E2-03、E2-08、E6-04、E6-09を挙げています。
原文・採点アンカーは再掲・言換えせず、原本ハッシュを参照します。列挙は網羅的ではなく、
違反認定でも項目除外の指示でもありません。研究用途と実際の不正利用等は区別して、
適用条件・必要な研究例外を人間が確認し、曖昧ならproviderや適切な専門家への確認を残します。
今回その照会を送信したり、代理で契約に同意したりはしません。

## A（推奨）：条件付き利用・保存・公表方針を採用し、未解決事項は停止条件に残す

- 第一当事者APIによる研究観測に限定し、実際の学生の成績決定、不正提出、競合モデル学習、
  安全制限やrate limitの回避に使いません。実在学生の個人情報を追加送信しません。
- 原応答は保存権限・保持条件を確認してから、非公開・アクセス制限付きでimmutableに保存します。
  coding資料は同じ人間への限定exportで、raw本体を変えません。Gitや公開データセットへ全応答を
  自動公開しません。非公開にするだけで保存許可が得られるわけでもありません。
- 公表は集計・方法を中心とし、必要最小限の引用も権利・出典・AI生成表示等を人間が別途確認します。
  providerや所属機関のお墨付きと表示せず、原記録と公開用の派生物を分けます。
- Googleは有料projectの契約状態を実行前に確認します。今回、課金設定や支払を変更しません。
  原文に注記を足す、安全設定を緩める、項目を削る等で条件を回避することもしません。
- 実際の契約、全項目のAUP適用、長期保存・公表の疑義が残る間は新しい正式観測を開始しません。
  恒久保存と契約上の保持条件が両立しなければ、開始前に適法な保存計画を確定する必要があります。
  3社に縮めたり、別モデルへ替えたりせず、過去rawの書換え・削除で問題を隠しません。

Aはこの方針だけです。「4社すべて利用条件クリア」「条件付きなら今すぐ送信可」という
判断ではありません。停止条件を残したまま、独立した次の倫理・機関ガバナンスの確認へ
進める案です。新用途のterms_reviewはPENDING、AIはFINALやattestation=trueへ変更しません。

## B：方針採用と次の確認を保留し、先に契約上の疑問を解消する

先に適用契約・providerの回答・必要な専門確認を揃えてから、この方針と倫理確認へ戻ります。
今回の依頼だけで連絡・外部送信はせず、その内容・宛先等は別途確認します。

いずれも旧W0の承認を延長せず、凍結文書・過去の観測・W01は変更しません。
credential確認やAPI送信、xAI、W01、mergeは行いません。日時・最終実行許可も別です。

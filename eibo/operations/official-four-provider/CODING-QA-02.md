# 確認②：単独codingの品質確認方法（未承認案）

基本方針Aは、所有者の明示的なチャット回答に基づいて別記録へ転記しました。
対象は[基本方針v0.1](scope-01.proposal.yaml)のSHA-256に限定されます。
[進行状況](decision-progress.yaml)が現在の確認位置を示し、初期のapproval-queue雛形や
元の基本方針案は変更しません。named protocol-ownerの最終承認、利用条件、倫理・
ガバナンス決定、件数、費用、日時、API送信の許可には拡張していません。

## A（推奨）：ご本人による、期間を空けた抽出再coding

一次codingは全件をご本人1名が行い、まず最初の判定を確定・保存します。
各社×各70項目から1件ずつ、事前に固定した乱数で選ぶ計280件を確認対象とする案です。
選び方と乱数は観測開始前に承認・固定し、対象を予定スケジュールから決めます。
一次codingの前に対象を固定し、回答内容や最初の点数で選び直しません。
対象が技術的欠測なら欠測のまま報告し、別回答への差替えやモデルAPIの再送信はしません。
NR（採点不能）も保存し、無理に0点へ変換しません。

初回codingの確定から7日以上あけ、別の盲検ID・順番で、同じ原文と同じ採点基準を使って
再codingします。最初の点数やprovider/model/wave情報は表示しません。
ただし、ご本人が内容や文体を覚えている可能性は残り、完全な盲検とは主張しません。

一次の反復数が10なら、対象は2,800件中280件（10%）、初回と再確認を合わせて最大
3,080件分のcodingです。反復数と一次codingの総作業量は次の確認で決めるため未承認です。
反復数が変わる場合は再確認の割合も変わり、1反復なら全件が再確認対象になります。
欠測等により比較可能な組数は280未満になりえます。

## 不一致を隠さず、元の判定を残す

一致率、1点以内の一致、点差の分布、各コードの一致、NRの変化、欠測を、社・領域別に
記録する記述的な監査です。NATIVEはCLOSEDと別枠にします。2点以上の点差やNRとの
不一致は理由を人間が確認する対象としますが、これは本計画の確認ルールであり、
妥当性が検証された「信頼性の合格基準」ではありません。

一致の集計は不一致を検討する前の2組の判定で固定し、高い点や平均を自動採用しません。
修正が必要なら理由・対象範囲・版を別記録に残し、初回・再確認の両判定も保存します。
比較に都合よく特定社や回答だけを修正せず、修正後の一致率で元の不一致を隠しません。
生の回答や凍結された採点アンカーは変更しません。

AI二次codingは使いません。自動化は入力漏れ・値の範囲・記録の対応・ハッシュ等の
形式確認に限定し、実質的な点数を付けたり書き換えたりしません。

## B：抽出件数や待機日数を調整してから決める

ご負担に応じて案を修正し、修正版を見てから採用します。BはAIによる一次採点や
既存コードの上書き、確認手順の省略を自動承認する選択肢ではありません。

## 方法論上の位置付け

This is a proposed descriptive within-coder audit, not an independent-rater
reliability study or proof of coding validity. Agreement and reliability are
distinct, and reporting must reflect the ordinal measurement level and the
study design. See Vanbelle, Engelhart and Blix (2024),
[the primary methods paper](https://link.springer.com/article/10.1186/s12874-024-02431-y).
The seven-day interval, one-per-cell workload and two-point review flag are EIBO
operational proposals, not requirements established by that paper. No power,
precision, reliability threshold, or memory-erasure guarantee is inferred.

旧Codebookの2名・150/200件のpilotを満たしたとは扱いません。この案はまだ未承認・
未実装・未実施です。採用しても正式プロトコルの凍結や観測開始の許可にはなりません。

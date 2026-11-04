# Kiến trúc LifeMate — tài liệu "tại sao"

> **Nguồn chuẩn cho mọi quy tắc hiện thực là [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md).**
> File này chỉ giữ **kiến trúc và lý do** của từng khối. Nếu hai file có ý khác nhau → `EXECUTION-PLAN.md` thắng, và phải sửa file này.
> Lịch sử các câu hỏi đã trả lời: [`Questions.md`](Questions.md) (record, không phải spec).

---

## 1. Bài toán và các ràng buộc cứng

ZAC 2026 — LifeMate: mỗi mẫu là một phiên thiết bị riêng (`ToolEnv` trên `state.json` riêng của mẫu). Agent nghe **audio tiếng Việt** và phải sinh **tool_calls** hợp lệ. BTC replay `tool_calls` trên state gốc, so với đáp án.

| Ràng buộc từ đề | Hệ quả thiết kế | Khối thực thi |
|---|---|---|
| Mọi lời gọi `env.call` đều bị ghi log và nộp. Ngoài phạm vi phải trả `[]` | **Không gọi tool nào, kể cả tool đọc, trước khi biết yêu cầu nằm trong phạm vi** | `scope.py` chạy trước `prefetch.py` |
| Cấm đọc `state.json`. ID thiết bị, danh bạ chỉ có qua tool đọc | Phải đọc trước (prefetch) rồi mới lập kế hoạch | `prefetch.py`, `lexicon.py` |
| Sai một tên, số tiền, giờ, ID là sai | Sửa lỗi nghe bằng từ vựng thật của môi trường; parser số/giờ bằng luật | `asr.py`, `resolver.py`, `vi_norm.py` |
| Mỗi mẫu chỉ một `ToolEnv`, lệnh ghi không hoàn tác | Planner sinh kế hoạch → code kiểm tra → mới thực thi. Không có "thử rồi sửa" trên lệnh ghi | `planner.py`, `gate.py`, `executor.py` |
| Mô hình 4B không fine-tune dễ bịa ID, thiếu tham số, hỏi/làm sai | Mọi kiểm tra tính hợp lệ lấy từ catalog (`required`, `enum`, `x-ref`, `x-one-of`) và dữ liệu đã đọc, **không** dựa vào việc mô hình tự khai | `gate.py` |
| Test có thể có tool/app lạ | Không hard-code tên tool/app. Mọi thứ đi qua catalog | `catalog.py` |
| Nhãn hỏi/làm/từ chối chỉ biết qua train | Pha 0 khảo sát nhãn thật trước khi cố định luật | `scripts/analyze_train.py` |

**Bổ sung (phát hiện khi đọc gói dữ liệu):**

| Ràng buộc | Hệ quả thiết kế | Khối thực thi |
|---|---|---|
| `env.call` ghi log **cả call bị từ chối** | Call rác phải bị chặn *trước* khi gọi; prefetch read tool cũng nằm trong `tool_calls` ⇒ prefetch phải có giới hạn | `gate.py`, `prefetch.py` |
| `canon()` bỏ field text tự do khỏi `state_hash` | Sai nội dung text **không lộ** trong hash nhưng **lộ** trong F1-call ⇒ metric ưu tiên là F1-call, và không được coi hash là mục tiêu duy nhất | `eval/metrics.py` |
| LLM và STT chạy qua API OpenAI-compatible | Không bundle model; tool call lấy từ `message.tool_calls` (structured) thay vì parse text | `llm.py`, `asr.py`, `apiclient.py` |

---

## 2. Luồng dữ liệu (một mẫu)

```
item + catalog
  ├─[1] ASR (chưa có snapshot): audio → n-best
  ├─[2] SCOPE: ngoài phạm vi? → trả [] và kết thúc (chưa gọi tool nào)
  ├─[3] PREFETCH: gọi tool kind=read → snapshot
  ├─[4] LEXICON + RESOLVER: gợi ý thực thể/số/giờ từ n-best + snapshot
  ├─[5] PROMPT + PLANNER (LLM qua API, tool-calling)
  ├─[6] GATE: kiểm tra tất định theo schema + snapshot
  ├─[7] EXECUTOR: validate → call (mỗi lệnh ghi đúng một lần); vòng B2 cho bước phụ thuộc
  └─► env.get_tool_calls(), env.get_state_hash()
```

ASR chạy **trước** prefetch để mẫu ngoài phạm vi không để lại log đọc nào. Hotwords lấy từ snapshot chỉ là bước tùy chọn.

---

## 3. Vì sao có từng khối

| Khối | Trách nhiệm | Lý do tồn tại |
|---|---|---|
| `apiclient.py` | Client OpenAI-compatible + retry/backoff | LLM và STT đều qua API; lỗi mạng không được làm sập lượt chạy |
| `catalog.py` | Schema tool của split → `Tool`; `to_llm_tools`; `resolve_tool_name` | Public test có **11 app / 34 tool chưa từng có ở train** ⇒ không được hard-code; mọi kiểm tra schema lấy từ đây |
| `prefetch.py` | Gọi read tool → snapshot | Cần ID/tên thật trước khi lập kế hoạch; nhưng call đọc **đều được nộp** ⇒ phải giới hạn số lượng |
| `lexicon.py` | Snapshot → `Entity`, `id` theo collection; cắt snapshot cho prompt | Biến dữ liệu thô thành thứ LLM dùng được, và là nguồn ID để sửa ID bịa |
| `vi_norm.py` | Parser số/giờ tiếng Việt | "năm trăm nghìn", "ba giờ chiều mai" — LLM 4B hay sai; luật thì không sai |
| `resolver.py` | Transcript + snapshot → `Hint` (tên/số/giờ) | Nối lời nói với đúng ID trong app; đây là nơi lỗi nghe được sửa |
| `asr.py` | Audio → n-best transcript | Điểm vào duy nhất của môi trường người dùng; có kiểm tra suy biến |
| `scope.py` | Có yêu cầu nằm trong phạm vi app đã cài không | Ngoài phạm vi phải trả `[]` — và **không được** để lại log đọc nào |
| `llm.py` | Gọi LLM, parse tool call, trả text | Tách "nói chuyện với LLM" khỏi "quyết định chạy tool" |
| `prompt.py` | System + user message cố định | Prompt là hợp đồng với LLM; đổi prompt = đổi hành vi agent |
| `planner.py` | LLM → danh sách call thô | Tách "LLM muốn gọi gì" khỏi "call nào được phép chạy" |
| `gate.py` | Kiểm tra tất định, sửa tham số, quyết định `ask`/`refuse` | **Module quan trọng nhất**: chặn ID bịa, tham số sai kiểu, enum sai, gọi trùng; và quyết định hỏi hay làm |
| `executor.py` | Thực thi call, vòng B2, chống lặp | Lệnh ghi không hoàn tác ⇒ chỉ gọi khi đã qua gate; vòng B2 cho bước phụ thuộp (đọc → biết ID → ghi) |
| `agent.py` | Ghép các bước theo đúng thứ tự, ghi debug | Giữ `infer()` gọn; đảm bảo scope luôn trước prefetch |
| `infer.py` | Vòng lặp trên split, xuất `submission.jsonl` | 1 dòng/mẫu, luôn đủ số dòng dù mẫu lỗi |
| `retrieval.py` | Few-shot BM25 (tùy chọn, M4) | Chỉ bật nếu đo ra tăng điểm trên held-out |

---

## 4. Vài quyết định đã chốt (vì sao)

| Quyết định | Lý do |
|---|---|
| Metric ưu tiên = **F1-call**, hash là chỉ số phụ | `zaic_tools/README.md` nói BTC "tính F1 trên call"; 124/1217 mẫu act **chỉ có read** nên state không đổi ⇒ không thể chỉ tối ưu hash |
| `PREFETCH_MAX_READS` nhỏ (mặc định 2) | Trung bình ~9,7 read tool prefetchable/mẫu nhưng gold chỉ có ~1,03 read call/mẫu ⇒ prefetch toàn bộ tụt precision |
| Gate **không dừng duyệt** khi gặp call thiếu tham số | Trong 217 mẫu ask, `ask` **luôn ở cuối**, 157 mẫu có call khác trước đó, 79 mẫu đã ghi write ⇒ dừng duyệt sẽ mất đúng các call gold vẫn có |
| `ASK_AFTER_PARTIAL = True` | 157/217 mẫu ask có call trước `ask` |
| Hỏi **đúng 1 tham số** khi thiếu `x-one-of` | Mỗi nhóm `x-one-of` trong cả 2 split đều đúng 1 tham số, và gold hỏi nhóm người dùng ngụ ý (`music.play` → `['playlist_id']`) |
| Không fine-tune | Đã chốt; `label` chỉ dùng để phân tích + few-shot |
| Không bundle model, gọi API | Container vòng private được gọi API; giảm rủi ro đóng gói |

Đặc tả hiện thực của các quyết định này nằm ở `EXECUTION-PLAN.md` (mục 4 dữ liệu đã verify, mục 6 đặc tả module, mục 11 việc còn mở).

---

## 5. Lộ trình

M0 → M1 → M3 → M2 → M4 → M5 → M6, tiêu chí nghiệm thu và lệnh kiểm tra: **`EXECUTION-PLAN.md` mục 8**.

---

## 6. Ranh giới

Ràng buộc cứng (8 điều) và danh sách **không làm** (anti-scope): **`EXECUTION-PLAN.md` mục 1 và mục 9**.

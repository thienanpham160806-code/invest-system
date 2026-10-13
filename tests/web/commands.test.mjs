// Parser lệnh terminal. Chạy: node --test tests/web/
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  COMMANDS,
  completeCommand,
  editDistance,
  parseCommand,
} from "../../lib/terminal/commands.ts";

const SYMBOLS = ["FPT", "FTS", "CMG", "ELC", "HPG", "VCB", "VNM", "SRC", "TOP", "CMP", "ACB", "ACV"];
const opts = {
  symbols: SYMBOLS,
  isSymbol: (s) => SYMBOLS.includes(s),
  resolveSector: (q) => (q.toLowerCase() === "ngân hàng" ? "ngan-hang" : null),
};

const parsed = (input, o = opts) => {
  const r = parseCommand(input, o);
  assert.ok(r.ok, `${input}: ${r.error}`);
  return r;
};
const failed = (input, o = opts) => {
  const r = parseCommand(input, o);
  assert.equal(r.ok, false, `${input} lẽ ra phải lỗi`);
  return r;
};

test("mã đơn và DES mở tổng quan", () => {
  for (const input of ["FPT", "fpt", "FPT DES", "  fpt   des ", "/FPT"]) {
    const r = parsed(input);
    assert.deepEqual(r.command, { kind: "ticker", symbol: "FPT", view: "DES" });
    assert.equal(r.href, "/stock/FPT");
  }
});

test("các chức năng trên mã", () => {
  const cases = {
    "FPT FA": "/stock/FPT?tab=bctc",
    "FPT RATIO": "/stock/FPT?tab=ratios",
    "FPT VAL": "/stock/FPT?tab=valuation",
    "FPT GP": "/stock/FPT?tab=technical",
    "FPT NEWS": "/stock/FPT?tab=news",
    "fpt pdf": "/report/FPT",
  };
  for (const [input, href] of Object.entries(cases)) assert.equal(parsed(input).href, href, input);
});

test("lệnh chung", () => {
  const cases = { TOP: "/co-hoi", MAP: "/#ban-do", MACRO: "/vi-mo", BT: "/backtest", SRC: "/nguon" };
  for (const [input, href] of Object.entries(cases)) {
    const r = parsed(input);
    assert.equal(r.command.kind, "global");
    assert.equal(r.href, href);
  }
  assert.equal(parsed("HELP").command.kind, "help");
  assert.equal(parsed("?").href, null);
});

test("CMP so sánh nhiều mã, nhận cả dấu phẩy, bỏ trùng", () => {
  const r = parsed("CMP FPT CMG ELC");
  assert.deepEqual(r.command, { kind: "compare", symbols: ["FPT", "CMG", "ELC"] });
  assert.equal(r.href, "/so-sanh?ma=FPT,CMG,ELC");
  assert.deepEqual(parsed("cmp fpt,cmg fpt").command.symbols, ["FPT", "CMG"]);
});

test("CMP lỗi: thiếu mã, mã sai, quá nhiều mã", () => {
  assert.match(failed("CMP FPT").error, /ít nhất 2 mã/);
  // trùng mã: không gợi ý lại chính lệnh lỗi (review Codex 6b98ca4)
  const dup = failed("CMP FPT FPT");
  assert.ok(!dup.suggestions.includes("CMP FPT FPT"));
  assert.equal(parseCommand(dup.suggestions[0], opts).ok, true);
  assert.deepEqual(failed("CMP FPT", { symbols: ["FPT"], isSymbol: (s) => s === "FPT" }).suggestions, []);
  const bad = failed("CMP FPT HPQ");
  assert.match(bad.error, /HPQ/);
  assert.ok(bad.suggestions.includes("CMP FPT HPG"));
  const many = ["FPT", "FTS", "CMG", "ELC", "HPG", "VCB", "VNM", "ACB", "ACV"];
  assert.match(failed(`CMP ${many.join(" ")}`).error, /tối đa 8/);
});

test("mã trùng từ khoá: lệnh chung khi gõ riêng, mã khi có chức năng", () => {
  const src = parsed("SRC");
  assert.equal(src.command.kind, "global");
  assert.match(src.note, /SRC DES/);
  assert.deepEqual(parsed("SRC DES").command, { kind: "ticker", symbol: "SRC", view: "DES" });
  assert.deepEqual(parsed("TOP FA").command, { kind: "ticker", symbol: "TOP", view: "FA" });
  // CMP một mình: so sánh cần >= 2 mã nên là mã CMP
  assert.deepEqual(parsed("CMP").command, { kind: "ticker", symbol: "CMP", view: "DES" });
  assert.deepEqual(parsed("CMP NEWS").command, { kind: "ticker", symbol: "CMP", view: "NEWS" });
  // không có danh sách mã thì không tự nhận MAP là cổ phiếu
  assert.equal(parseCommand("MAP").note, undefined);
});

test("SECT nhận tên ngành tiếng Việt, giữ chữ thường, có slug khi khớp", () => {
  const r = parsed("SECT Ngân hàng");
  assert.deepEqual(r.command, { kind: "sector", query: "Ngân hàng", slug: "ngan-hang" });
  assert.equal(r.href, "/nganh/ngan-hang");
  assert.equal(parsed("sect Bất động sản").href, `/nganh?q=${encodeURIComponent("Bất động sản")}`);
  assert.match(failed("SECT").error, /tên ngành/);
});

test("gợi ý gần đúng khi gõ sai", () => {
  assert.ok(failed("FPT FAA").suggestions.includes("FPT FA"));
  assert.ok(failed("FPT RATO").suggestions.includes("FPT RATIO"));
  assert.ok(failed("FPT VLA").suggestions.includes("FPT VAL"));    // đảo chữ
  assert.ok(failed("MACOR").suggestions.includes("MACRO"));
  assert.ok(failed("HELPP").suggestions.includes("HELP"));
  assert.ok(failed("FTP").suggestions.includes("FPT"));            // mã gõ đảo
  assert.ok(failed("FTP FA").suggestions.includes("FPT FA"));
  assert.ok(failed("SECTT Ngân hàng").suggestions.includes("SECT Ngân hàng"));
  assert.ok(failed("FPT XYZ").suggestions.includes("FPT DES"));    // không gần cái nào: gợi ý mặc định
});

test("nhiều mã không có CMP thì gợi ý CMP", () => {
  assert.deepEqual(failed("FPT CMG HPG").suggestions, ["CMP FPT CMG HPG"]);
});

test("đầu vào rỗng và rác", () => {
  assert.match(failed("").error, /Nhập lệnh/);
  assert.match(failed("   ").error, /Nhập lệnh/);
  failed("!!!");
  failed("FPT FA EXTRA");
});

test("không có danh sách mã: chỉ kiểm tra dạng 3 ký tự", () => {
  assert.deepEqual(parseCommand("ABC FA").command, { kind: "ticker", symbol: "ABC", view: "FA" });
  assert.equal(parseCommand("ABCD").ok, false);
  assert.equal(parseCommand("1AB").ok, false);
});

test("tự hoàn thành", () => {
  assert.deepEqual(completeCommand("FP", opts), ["FPT"]);
  assert.ok(completeCommand("MA", opts).includes("MACRO") && completeCommand("MA", opts).includes("MAP"));
  assert.deepEqual(completeCommand("FPT R", opts), ["FPT RATIO"]);
  assert.equal(completeCommand("FPT ", opts).length, 7);
  assert.deepEqual(completeCommand("CMP FPT C", opts), ["CMP FPT CMG", "CMP FPT CMP"]);
  assert.ok(!completeCommand("CMP FPT ", opts).includes("CMP FPT FPT"));
  assert.ok(completeCommand("", opts).length > 0);
  assert.deepEqual(completeCommand("SECT Ng", opts), []);
});

test("bảng lệnh liệt kê đủ lệnh và ví dụ đều hợp lệ", () => {
  for (const c of COMMANDS) {
    const r = parseCommand(c.example, opts);
    assert.ok(r.ok, `ví dụ "${c.example}" không chạy: ${r.error}`);
  }
  const syntaxes = COMMANDS.map((c) => c.syntax.split(" ")[0]);
  for (const k of ["CMP", "SECT", "TOP", "MAP", "MACRO", "BT", "SRC"]) assert.ok(syntaxes.includes(k), k);
});

test("editDistance", () => {
  assert.equal(editDistance("FPT", "FPT"), 0);
  assert.equal(editDistance("FTP", "FPT"), 1);
  assert.equal(editDistance("MACOR", "MACRO"), 1);
  assert.equal(editDistance("", "ABC"), 3);
});

test("đầu vào rất dài bị chặn trước khi so gần đúng (review Codex 6b98ca4)", () => {
  const universe = Array.from({ length: 1500 }, (_, i) => `A${String(i).padStart(2, "0")}`.slice(0, 3) + i);
  const big = { symbols: universe, isSymbol: () => false };
  const t0 = performance.now();
  assert.match(parseCommand("X".repeat(1_000_000), big).error, /quá dài/);
  assert.deepEqual(completeCommand("X".repeat(1_000_000), big), []);
  assert.ok(failed("Q".repeat(150), big).suggestions.length === 0);
  assert.ok(performance.now() - t0 < 500, "phải trả lời gần như tức thì");
});

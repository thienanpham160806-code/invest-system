// Parser lệnh terminal kiểu Bloomberg — thuần logic, không phụ thuộc React/DOM.
// Test: node --test tests/web/  (Node ≥ 23 tự bỏ kiểu TypeScript; tránh enum/namespace).
//
//   FPT | FPT DES   tổng quan          CMP FPT CMG ELC   so sánh
//   FPT FA          BCTC               SECT <ngành>      ngành
//   FPT RATIO       chỉ số             TOP               bảng cơ hội
//   FPT VAL         định giá           MAP               bản đồ thị trường
//   FPT GP          biểu đồ giá        MACRO             vĩ mô
//   FPT NEWS        tin tức            BT                backtest
//   FPT PDF         báo cáo PDF        SRC               nguồn dữ liệu
//                                      HELP | ?          bảng lệnh
//
// CMP, SRC, TOP cũng là mã niêm yết thật. Gõ riêng một từ thì là lệnh chung
// (riêng CMP: so sánh cần ≥ 2 mã nên "CMP" một mình là mã CMP); muốn mở cổ
// phiếu thì thêm chức năng: "SRC DES", "TOP FA".

export type TickerView = "DES" | "FA" | "RATIO" | "VAL" | "GP" | "NEWS" | "PDF";
export type GlobalKeyword = "TOP" | "MAP" | "MACRO" | "BT" | "SRC";

export type Command =
  | { kind: "ticker"; symbol: string; view: TickerView }
  | { kind: "compare"; symbols: string[] }
  | { kind: "sector"; query: string; slug: string | null }
  | { kind: "global"; keyword: GlobalKeyword }
  | { kind: "help" };

export type ParseResult =
  | { ok: true; command: Command; href: string | null; note?: string }
  | { ok: false; error: string; suggestions: string[] };

export type ParseOptions = {
  /** Mã có trong universe? Không truyền thì chỉ kiểm tra dạng (3 ký tự, bắt đầu bằng chữ). */
  isSymbol?: (symbol: string) => boolean;
  /** Danh sách mã để gợi ý gần đúng / tự hoàn thành. */
  symbols?: readonly string[];
  /** Tên ngành → slug /nganh/[slug]; null nếu không khớp. */
  resolveSector?: (query: string) => string | null;
};

export type CommandInfo = { syntax: string; example: string; description: string };

export const TICKER_VIEWS: Record<TickerView, { tab: string; label: string }> = {
  DES: { tab: "overview", label: "Tổng quan" },
  FA: { tab: "bctc", label: "Báo cáo tài chính" },
  RATIO: { tab: "ratios", label: "Chỉ số tài chính" },
  VAL: { tab: "valuation", label: "Định giá" },
  GP: { tab: "technical", label: "Biểu đồ giá & kỹ thuật" },
  NEWS: { tab: "news", label: "Tin tức" },
  PDF: { tab: "report", label: "Báo cáo PDF" },
};

export const GLOBAL_ROUTES: Record<GlobalKeyword, { href: string; label: string }> = {
  TOP: { href: "/co-hoi", label: "Bảng cơ hội đầu tư" },
  MAP: { href: "/#ban-do", label: "Bản đồ thị trường" },
  MACRO: { href: "/vi-mo", label: "Vĩ mô trong nước & quốc tế" },
  BT: { href: "/backtest", label: "Kết quả backtest" },
  SRC: { href: "/nguon", label: "Nguồn dữ liệu" },
};

export const MAX_COMPARE = 8;
export const MAX_INPUT_LENGTH = 200;
const SYMBOL_RE = /^[A-Z][A-Z0-9]{2}$/;
const HELP_WORDS = new Set(["HELP", "?"]);

export const COMMANDS: CommandInfo[] = [
  { syntax: "<MÃ> [DES]", example: "FPT", description: "Tổng quan cổ phiếu" },
  ...(["FA", "RATIO", "VAL", "GP", "NEWS", "PDF"] as TickerView[]).map((v) => ({
    syntax: `<MÃ> ${v}`, example: `FPT ${v}`, description: TICKER_VIEWS[v].label,
  })),
  { syntax: "CMP <MÃ> <MÃ> …", example: "CMP FPT CMG ELC", description: `So sánh 2–${MAX_COMPARE} mã` },
  { syntax: "SECT <ngành>", example: "SECT Ngân hàng", description: "Trang ngành" },
  ...(Object.keys(GLOBAL_ROUTES) as GlobalKeyword[]).map((k) => ({
    syntax: k, example: k, description: GLOBAL_ROUTES[k].label,
  })),
  { syntax: "HELP | ?", example: "?", description: "Bảng lệnh và phím tắt" },
];

const KEYWORDS = ["CMP", "SECT", "HELP", ...Object.keys(GLOBAL_ROUTES)];
const VIEWS = Object.keys(TICKER_VIEWS) as TickerView[];

// ------------------------------------------------------------------ tiện ích

/** Khoảng cách Damerau–Levenshtein (bản optimal string alignment). */
export function editDistance(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) =>
    Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[a.length][b.length];
}

function closest(word: string, candidates: readonly string[], limit = 3): string[] {
  const maxDist = word.length <= 3 ? 1 : 2;
  return candidates
    .filter((c) => Math.abs(c.length - word.length) <= maxDist) // bỏ sớm, tránh O(n·m) vô ích
    .map((c) => ({ c, dist: editDistance(word, c) }))
    .filter((x) => x.dist <= maxDist && x.c !== word)
    .sort((x, y) => x.dist - y.dist || x.c.localeCompare(y.c))
    .slice(0, limit)
    .map((x) => x.c);
}

function isView(word: string | undefined): word is TickerView {
  return word !== undefined && (VIEWS as string[]).includes(word);
}

function symbolOk(word: string, opts: ParseOptions): boolean {
  return opts.isSymbol ? opts.isSymbol(word) : SYMBOL_RE.test(word);
}

function looksLikeSymbol(word: string, opts: ParseOptions): boolean {
  return SYMBOL_RE.test(word) || Boolean(opts.isSymbol?.(word));
}

function fail(error: string, suggestions: string[] = []): ParseResult {
  return { ok: false, error, suggestions: [...new Set(suggestions)].slice(0, 5) };
}

export function commandHref(cmd: Command): string | null {
  switch (cmd.kind) {
    case "ticker":
      if (cmd.view === "PDF") return `/report/${cmd.symbol}`;
      return cmd.view === "DES" ? `/stock/${cmd.symbol}` : `/stock/${cmd.symbol}?tab=${TICKER_VIEWS[cmd.view].tab}`;
    case "compare":
      return `/so-sanh?ma=${cmd.symbols.join(",")}`;
    case "sector":
      return cmd.slug ? `/nganh/${cmd.slug}` : `/nganh?q=${encodeURIComponent(cmd.query)}`;
    case "global":
      return GLOBAL_ROUTES[cmd.keyword].href;
    case "help":
      return null;
  }
}

function ok(command: Command, note?: string): ParseResult {
  return note ? { ok: true, command, href: commandHref(command), note } : { ok: true, command, href: commandHref(command) };
}

// ------------------------------------------------------------------ parser

export function parseCommand(input: string, opts: ParseOptions = {}): ParseResult {
  const raw = input.trim().replace(/^[/>:]+\s*/, "");
  if (!raw) return fail("Nhập lệnh, ví dụ: FPT, FPT FA, CMP FPT CMG, TOP. Gõ ? để xem bảng lệnh.");
  if (raw.length > MAX_INPUT_LENGTH) return fail(`Lệnh quá dài (tối đa ${MAX_INPUT_LENGTH} ký tự).`);
  const original = raw.split(/\s+/);
  const tokens = original.map((t) => t.toUpperCase());
  const [head, ...rest] = tokens;

  if (HELP_WORDS.has(head) && rest.length === 0) return ok({ kind: "help" });

  if (head === "SECT") {
    const query = original.slice(1).join(" ");
    if (!query) return fail("SECT cần tên ngành, ví dụ: SECT Ngân hàng.", ["SECT Ngân hàng", "SECT Bất động sản"]);
    return ok({ kind: "sector", query, slug: opts.resolveSector?.(query) ?? null });
  }

  if (head in GLOBAL_ROUTES && rest.length === 0) {
    const keyword = head as GlobalKeyword;
    const note = opts.isSymbol?.(keyword) ? `${keyword} cũng là mã cổ phiếu: gõ "${keyword} DES" để mở mã.` : undefined;
    return ok({ kind: "global", keyword }, note);
  }

  if (head === "CMP" && rest.length > 0 && !isView(rest[0])) {
    const symbols = [...new Set(rest.flatMap((t) => t.split(",")).filter(Boolean))];
    const bad = symbols.filter((s) => !symbolOk(s, opts));
    if (bad.length) {
      const near = bad.flatMap((s) => closest(s, opts.symbols ?? []));
      return fail(`Không nhận ra mã: ${bad.join(", ")}.`, near.map((n) => `CMP ${symbols.map((s) => (bad.includes(s) ? n : s)).join(" ")}`));
    }
    if (symbols.length < 2) {
      const other = (opts.symbols ?? []).find((s) => s !== symbols[0]);
      return fail("CMP cần ít nhất 2 mã khác nhau, ví dụ: CMP FPT CMG ELC.", other ? [`CMP ${symbols[0]} ${other}`] : []);
    }
    if (symbols.length > MAX_COMPARE) return fail(`CMP so sánh tối đa ${MAX_COMPARE} mã.`, [`CMP ${symbols.slice(0, MAX_COMPARE).join(" ")}`]);
    return ok({ kind: "compare", symbols });
  }

  if (looksLikeSymbol(head, opts) && rest.length <= 1) {
    const view = rest[0] ?? "DES";
    if (!symbolOk(head, opts)) {
      const near = [...closest(head, opts.symbols ?? []), ...closest(head, KEYWORDS)];
      return fail(`Không có mã ${head} trong danh sách niêm yết.`, near.map((n) => (rest.length ? `${n} ${view}` : n)));
    }
    if (!isView(view)) {
      const near = closest(view, VIEWS);
      return fail(`Không rõ chức năng "${view}" cho ${head}.`, (near.length ? near : ["DES", "FA"]).map((v) => `${head} ${v}`));
    }
    return ok({ kind: "ticker", symbol: head, view });
  }

  if (looksLikeSymbol(head, opts) && rest.every((t) => looksLikeSymbol(t, opts) && !isView(t))) {
    return fail("Nhiều mã liền nhau: muốn so sánh thì thêm CMP phía trước.", [`CMP ${tokens.join(" ")}`]);
  }

  const near = [...closest(head, KEYWORDS), ...closest(head, opts.symbols ?? [])];
  const suffix = rest.length ? ` ${original.slice(1).join(" ")}` : "";
  return fail(`Không hiểu lệnh "${raw}". Gõ ? để xem bảng lệnh.`, near.map((n) => `${n}${suffix}`));
}

// ------------------------------------------------------------------ tự hoàn thành

/** Gợi ý hoàn thành cho nội dung đang gõ (tối đa `limit` dòng, đã viết hoa). */
export function completeCommand(input: string, opts: ParseOptions = {}, limit = 8): string[] {
  if (input.length > MAX_INPUT_LENGTH) return [];
  const text = input.replace(/^[/>:]+\s*/, "").toUpperCase();
  const tokens = text.split(/\s+/).filter(Boolean);
  const trailingSpace = /\s$/.test(input);
  const symbols = opts.symbols ?? [];
  if (tokens.length === 0) return COMMANDS.map((c) => c.example).slice(0, limit);

  if (tokens.length === 1 && !trailingSpace) {
    const word = tokens[0];
    const keywordHits = KEYWORDS.filter((k) => k.startsWith(word));
    const symbolHits = symbols.filter((s) => s.startsWith(word));
    return [...new Set([...symbolHits, ...keywordHits])].slice(0, limit);
  }

  const [head, ...rest] = tokens;
  const partial = trailingSpace ? "" : rest[rest.length - 1] ?? "";
  const done = trailingSpace ? rest : rest.slice(0, -1);
  if (head === "CMP") {
    const prefix = ["CMP", ...done].join(" ");
    return symbols.filter((s) => s.startsWith(partial) && !done.includes(s)).slice(0, limit).map((s) => `${prefix} ${s}`);
  }
  if (head === "SECT") return [];
  if (done.length === 0 && symbolOk(head, opts)) {
    return VIEWS.filter((v) => v.startsWith(partial)).map((v) => `${head} ${v}`).slice(0, limit);
  }
  return [];
}

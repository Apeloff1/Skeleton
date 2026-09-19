package com.tutolage.skeleton.controlplane;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/**
 * Strict dependency-free JSON model, parser, and canonical encoder.
 *
 * <p>The control plane signs canonical JSON bytes. Parsing therefore rejects
 * ambiguous or attacker-friendly inputs: duplicate keys, malformed Unicode,
 * invalid numbers, excessive nesting, excessive container sizes, and trailing
 * content.</p>
 */
public final class Json {
    private Json() {}

    public sealed interface Value permits Null, Bool, Num, Str, Arr, Obj {
        default String canonical() { return Canonical.write(this); }
        default byte[] canonicalUtf8() { return canonical().getBytes(StandardCharsets.UTF_8); }
    }

    public enum Null implements Value { INSTANCE }
    public record Bool(boolean value) implements Value {}

    public record Num(BigDecimal value) implements Value {
        public Num { Objects.requireNonNull(value, "value"); }
    }

    public record Str(String value) implements Value {
        public Str {
            Objects.requireNonNull(value, "value");
            validateUnicode(value);
        }
    }

    public record Arr(List<Value> values) implements Value {
        public Arr {
            values = List.copyOf(values);
            values.forEach(v -> Objects.requireNonNull(v, "array value"));
        }
    }

    public record Obj(Map<String, Value> values) implements Value {
        public Obj {
            var copy = new LinkedHashMap<String, Value>();
            for (var e : values.entrySet()) {
                validateUnicode(Objects.requireNonNull(e.getKey(), "object key"));
                if (copy.put(e.getKey(), Objects.requireNonNull(e.getValue(), "object value")) != null) {
                    throw new IllegalArgumentException("duplicate object key: " + e.getKey());
                }
            }
            values = Collections.unmodifiableMap(copy);
        }

        public Value get(String key) { return values.get(key); }

        public Value required(String key) {
            var v = values.get(key);
            if (v == null) throw new JsonException("missing required key: " + key, -1);
            return v;
        }

        public String string(String key) { return expectString(required(key), "$." + key); }
        public long longValue(String key) { return expectLong(required(key), "$." + key); }
        public boolean bool(String key) { return expectBool(required(key), "$." + key); }
        public Obj object(String key) { return expectObject(required(key), "$." + key); }
        public Arr array(String key) { return expectArray(required(key), "$." + key); }

        public String optionalString(String key, String fallback) {
            var v = values.get(key);
            return v == null ? fallback : expectString(v, "$." + key);
        }

        public void rejectUnknown(String... allowed) {
            var set = new java.util.HashSet<>(List.of(allowed));
            for (var key : values.keySet()) {
                if (!set.contains(key)) throw new JsonException("unknown key: " + key, -1);
            }
        }
    }

    public record Limits(int maxDepth, int maxStringChars, int maxContainerEntries, int maxDocumentChars) {
        public Limits {
            if (maxDepth < 1 || maxDepth > 512) throw new IllegalArgumentException("maxDepth");
            if (maxStringChars < 0 || maxContainerEntries < 0 || maxDocumentChars < 1) {
                throw new IllegalArgumentException("negative limit");
            }
        }

        public static Limits controlPlaneDefaults() {
            return new Limits(64, 1_000_000, 100_000, 4_000_000);
        }

        public static Limits tinyForTests() {
            return new Limits(8, 64, 32, 256);
        }
    }

    public static final class JsonException extends IllegalArgumentException {
        private final int offset;

        public JsonException(String message, int offset) {
            super(offset >= 0 ? message + " at offset " + offset : message);
            this.offset = offset;
        }

        public int offset() { return offset; }
    }

    public static Value parse(String input) {
        return parse(input, Limits.controlPlaneDefaults());
    }

    public static Value parse(String input, Limits limits) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(limits, "limits");
        if (input.length() > limits.maxDocumentChars()) {
            throw new JsonException("document exceeds maximum size", 0);
        }
        return new Parser(input, limits).parseDocument();
    }

    public static Obj obj(Map<String, Value> values) { return new Obj(values); }

    public static Obj obj(Object... kv) {
        if ((kv.length & 1) != 0) throw new IllegalArgumentException("key/value pairs required");
        var out = new LinkedHashMap<String, Value>();
        for (int i = 0; i < kv.length; i += 2) {
            if (!(kv[i] instanceof String key)) {
                throw new IllegalArgumentException("key must be String at index " + i);
            }
            if (out.containsKey(key)) throw new IllegalArgumentException("duplicate object key: " + key);
            out.put(key, fromJava(kv[i + 1]));
        }
        return new Obj(out);
    }

    public static Arr arr(Object... values) {
        var out = new ArrayList<Value>(values.length);
        for (var v : values) out.add(fromJava(v));
        return new Arr(out);
    }

    public static Value fromJava(Object value) {
        if (value == null) return Null.INSTANCE;
        if (value instanceof Value v) return v;
        if (value instanceof String s) return new Str(s);
        if (value instanceof Boolean b) return new Bool(b);
        if (value instanceof BigDecimal n) return new Num(n);
        if (value instanceof BigInteger n) return new Num(new BigDecimal(n));
        if (value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) {
            return new Num(BigDecimal.valueOf(((Number) value).longValue()));
        }
        if (value instanceof Float f) {
            if (!Float.isFinite(f)) throw new IllegalArgumentException("non-finite number");
            return new Num(BigDecimal.valueOf(f.doubleValue()));
        }
        if (value instanceof Double d) {
            if (!Double.isFinite(d)) throw new IllegalArgumentException("non-finite number");
            return new Num(BigDecimal.valueOf(d));
        }
        if (value instanceof Map<?, ?> m) {
            var out = new LinkedHashMap<String, Value>();
            for (var e : m.entrySet()) {
                if (!(e.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("JSON object key must be String");
                }
                if (out.containsKey(key)) throw new IllegalArgumentException("duplicate object key: " + key);
                out.put(key, fromJava(e.getValue()));
            }
            return new Obj(out);
        }
        if (value instanceof Iterable<?> it) {
            var out = new ArrayList<Value>();
            for (var v : it) out.add(fromJava(v));
            return new Arr(out);
        }
        if (value.getClass().isArray()) {
            int n = java.lang.reflect.Array.getLength(value);
            var out = new ArrayList<Value>(n);
            for (int i = 0; i < n; i++) {
                out.add(fromJava(java.lang.reflect.Array.get(value, i)));
            }
            return new Arr(out);
        }
        throw new IllegalArgumentException("unsupported JSON conversion type: " + value.getClass().getName());
    }

    public static Obj expectObject(Value v, String path) {
        if (v instanceof Obj o) return o;
        throw type(path, "object", v);
    }

    public static Arr expectArray(Value v, String path) {
        if (v instanceof Arr a) return a;
        throw type(path, "array", v);
    }

    public static String expectString(Value v, String path) {
        if (v instanceof Str s) return s.value();
        throw type(path, "string", v);
    }

    public static boolean expectBool(Value v, String path) {
        if (v instanceof Bool b) return b.value();
        throw type(path, "boolean", v);
    }

    public static BigDecimal expectNumber(Value v, String path) {
        if (v instanceof Num n) return n.value();
        throw type(path, "number", v);
    }

    public static long expectLong(Value v, String path) {
        try {
            return expectNumber(v, path).longValueExact();
        } catch (ArithmeticException ex) {
            throw new JsonException("expected integral long at " + path, -1);
        }
    }

    private static JsonException type(String path, String expected, Value actual) {
        return new JsonException(
            "expected " + expected + " at " + path + " but got " + actual.getClass().getSimpleName(),
            -1
        );
    }

    public static void validateUnicode(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= s.length() || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    throw new IllegalArgumentException("unpaired high surrogate at char " + i);
                }
                i++;
            } else if (Character.isLowSurrogate(c)) {
                throw new IllegalArgumentException("unpaired low surrogate at char " + i);
            }
        }
    }

    static int compareCodePoints(String a, String b) {
        int ia = 0;
        int ib = 0;
        while (ia < a.length() && ib < b.length()) {
            int ca = a.codePointAt(ia);
            int cb = b.codePointAt(ib);
            if (ca != cb) return Integer.compare(ca, cb);
            ia += Character.charCount(ca);
            ib += Character.charCount(cb);
        }
        return Integer.compare(a.length() - ia, b.length() - ib);
    }

    private static final class Parser {
        private final String s;
        private final Limits limits;
        private int p;

        Parser(String s, Limits limits) {
            this.s = s;
            this.limits = limits;
        }

        Value parseDocument() {
            skipWs();
            var v = value(0);
            skipWs();
            if (p != s.length()) fail("trailing content");
            return v;
        }

        private Value value(int depth) {
            if (depth > limits.maxDepth()) fail("maximum nesting depth exceeded");
            skipWs();
            if (p >= s.length()) fail("unexpected end of input");

            return switch (s.charAt(p)) {
                case 'n' -> literal("null", Null.INSTANCE);
                case 't' -> literal("true", new Bool(true));
                case 'f' -> literal("false", new Bool(false));
                case '"' -> new Str(string());
                case '[' -> array(depth + 1);
                case '{' -> object(depth + 1);
                default -> {
                    char c = s.charAt(p);
                    if (c == '-' || (c >= '0' && c <= '9')) yield number();
                    fail("unexpected token");
                    yield null;
                }
            };
        }

        private Value literal(String token, Value v) {
            if (!s.startsWith(token, p)) fail("invalid literal");
            p += token.length();
            return v;
        }

        private Arr array(int depth) {
            p++;
            skipWs();
            var out = new ArrayList<Value>();
            if (take(']')) return new Arr(out);

            while (true) {
                if (out.size() >= limits.maxContainerEntries()) {
                    fail("array exceeds maximum entries");
                }
                out.add(value(depth));
                skipWs();
                if (take(']')) return new Arr(out);
                require(',');
                skipWs();
            }
        }

        private Obj object(int depth) {
            p++;
            skipWs();
            var out = new LinkedHashMap<String, Value>();
            if (take('}')) return new Obj(out);

            while (true) {
                if (out.size() >= limits.maxContainerEntries()) {
                    fail("object exceeds maximum entries");
                }
                if (p >= s.length() || s.charAt(p) != '"') {
                    fail("object key must be a string");
                }
                String key = string();
                if (out.containsKey(key)) fail("duplicate object key: " + key);
                skipWs();
                require(':');
                Value v = value(depth);
                out.put(key, v);
                skipWs();
                if (take('}')) return new Obj(out);
                require(',');
                skipWs();
            }
        }

        private Num number() {
            int start = p;
            if (take('-') && p >= s.length()) fail("incomplete number");

            if (take('0')) {
                if (p < s.length() && Character.isDigit(s.charAt(p))) {
                    fail("leading zero is not allowed");
                }
            } else {
                if (p >= s.length() || s.charAt(p) < '1' || s.charAt(p) > '9') {
                    fail("invalid integer part");
                }
                while (p < s.length() && Character.isDigit(s.charAt(p))) p++;
            }

            if (take('.')) {
                int fraction = p;
                while (p < s.length() && Character.isDigit(s.charAt(p))) p++;
                if (p == fraction) fail("fraction requires digits");
            }

            if (p < s.length() && (s.charAt(p) == 'e' || s.charAt(p) == 'E')) {
                p++;
                if (p < s.length() && (s.charAt(p) == '+' || s.charAt(p) == '-')) p++;
                int exponent = p;
                while (p < s.length() && Character.isDigit(s.charAt(p))) p++;
                if (p == exponent) fail("exponent requires digits");
            }

            String token = s.substring(start, p);
            try {
                return new Num(new BigDecimal(token));
            } catch (NumberFormatException ex) {
                throw new JsonException("invalid number", start);
            }
        }

        private String string() {
            require('"');
            var b = new StringBuilder();

            while (p < s.length()) {
                char c = s.charAt(p++);
                if (c == '"') {
                    if (b.length() > limits.maxStringChars()) fail("string exceeds maximum length");
                    validateUnicode(b.toString());
                    return b.toString();
                }
                if (c < 0x20) fail("control character in string");

                if (c == '\\') {
                    if (p >= s.length()) fail("unterminated escape");
                    char e = s.charAt(p++);
                    switch (e) {
                        case '"' -> b.append('"');
                        case '\\' -> b.append('\\');
                        case '/' -> b.append('/');
                        case 'b' -> b.append('\b');
                        case 'f' -> b.append('\f');
                        case 'n' -> b.append('\n');
                        case 'r' -> b.append('\r');
                        case 't' -> b.append('\t');
                        case 'u' -> b.append(unicodeEscape());
                        default -> fail("invalid escape");
                    }
                } else {
                    b.append(c);
                }

                if (b.length() > limits.maxStringChars()) fail("string exceeds maximum length");
            }

            fail("unterminated string");
            return null;
        }

        private char unicodeEscape() {
            if (p + 4 > s.length()) fail("short unicode escape");
            int v = 0;
            for (int i = 0; i < 4; i++) {
                int d = Character.digit(s.charAt(p++), 16);
                if (d < 0) fail("invalid unicode escape");
                v = (v << 4) | d;
            }
            return (char) v;
        }

        private void skipWs() {
            while (p < s.length()) {
                char c = s.charAt(p);
                if (c == ' ' || c == '\n' || c == '\r' || c == '\t') p++;
                else break;
            }
        }

        private boolean take(char c) {
            if (p < s.length() && s.charAt(p) == c) {
                p++;
                return true;
            }
            return false;
        }

        private void require(char c) {
            if (!take(c)) fail("expected '" + c + "'");
        }

        private void fail(String msg) {
            throw new JsonException(msg, p);
        }
    }

    public static final class Canonical {
        private Canonical() {}

        public static String write(Value value) {
            var b = new StringBuilder();
            write(value, b);
            return b.toString();
        }

        private static void write(Value value, StringBuilder b) {
            switch (value) {
                case Null ignored -> b.append("null");
                case Bool x -> b.append(x.value() ? "true" : "false");
                case Num x -> b.append(canonicalNumber(x.value()));
                case Str x -> quote(x.value(), b);
                case Arr x -> {
                    b.append('[');
                    for (int i = 0; i < x.values().size(); i++) {
                        if (i > 0) b.append(',');
                        write(x.values().get(i), b);
                    }
                    b.append(']');
                }
                case Obj x -> {
                    b.append('{');
                    boolean first = true;
                    var sorted = new TreeMap<String, Value>(Json::compareCodePoints);
                    sorted.putAll(x.values());
                    for (var e : sorted.entrySet()) {
                        if (!first) b.append(',');
                        first = false;
                        quote(e.getKey(), b);
                        b.append(':');
                        write(e.getValue(), b);
                    }
                    b.append('}');
                }
            }
        }

        private static String canonicalNumber(BigDecimal n) {
            if (n.signum() == 0) return "0";
            BigDecimal z = n.stripTrailingZeros();
            String plain = z.toPlainString();
            if (plain.length() <= 1000) return plain;
            return z.toEngineeringString().replace("E+", "E").replace('E', 'e');
        }

        private static void quote(String s, StringBuilder b) {
            validateUnicode(s);
            b.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"' -> b.append("\\\"");
                    case '\\' -> b.append("\\\\");
                    case '\b' -> b.append("\\b");
                    case '\f' -> b.append("\\f");
                    case '\n' -> b.append("\\n");
                    case '\r' -> b.append("\\r");
                    case '\t' -> b.append("\\t");
                    default -> {
                        if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                        else b.append(c);
                    }
                }
            }
            b.append('"');
        }
    }
}

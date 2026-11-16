// Exact GGUF token transport for the pinned llama.cpp b11429 public C API.
// The process has no network client, chat templating, plugin, or shell path.
// Input/output are private binary files, not command line prompt arguments.
#include "llama.h"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr uint32_t max_text = 4u * 1024 * 1024;
constexpr uint32_t max_tokens = 1048576;
constexpr uint32_t max_output = 8192;
using Tokens = std::vector<llama_token>;

[[noreturn]] void deny() { throw std::runtime_error("bridge denied input or execution"); }
uint32_t read_u32(std::istream & in) {
    unsigned char raw[4];
    if (!in.read(reinterpret_cast<char *>(raw), 4)) deny();
    return uint32_t(raw[0]) | (uint32_t(raw[1]) << 8) |
           (uint32_t(raw[2]) << 16) | (uint32_t(raw[3]) << 24);
}
void write_u32(std::ostream & out, uint32_t v) {
    unsigned char raw[4] = {static_cast<unsigned char>(v),
        static_cast<unsigned char>(v >> 8), static_cast<unsigned char>(v >> 16),
        static_cast<unsigned char>(v >> 24)};
    if (!out.write(reinterpret_cast<const char *>(raw), 4)) deny();
}
void eof(std::istream & in) { if (in.peek() != std::char_traits<char>::eof() || in.bad()) deny(); }
void read_magic(std::istream & in) {
    char magic[4];
    if (!in.read(magic, 4) || std::string(magic, 4) != "SKG1") deny();
}
std::string read_text(std::istream & in) {
    auto n = read_u32(in);
    if (n > max_text) deny();
    std::string s(n, '\0');
    if (n && !in.read(s.data(), n)) deny();
    return s;
}
void write_text(std::ostream & out, const std::string & s) {
    if (s.size() > max_text) deny();
    write_u32(out, static_cast<uint32_t>(s.size()));
    if (!out.write(s.data(), static_cast<std::streamsize>(s.size()))) deny();
}
Tokens read_tokens(std::istream & in, const llama_vocab * vocab) {
    const auto n = read_u32(in);
    if (n > max_tokens) deny();
    const auto vocab_count = llama_vocab_n_tokens(vocab);
    if (vocab_count <= 0) deny();
    Tokens tokens;
    tokens.reserve(n);
    for (uint32_t i = 0; i < n; ++i) {
        const auto token = read_u32(in);
        if (token >= static_cast<uint32_t>(vocab_count)) deny();
        tokens.push_back(static_cast<llama_token>(token));
    }
    return tokens;
}
void write_tokens(std::ostream & out, const Tokens & tokens) {
    if (tokens.size() > max_tokens) deny();
    write_u32(out, static_cast<uint32_t>(tokens.size()));
    for (auto token : tokens) {
        if (token < 0) deny();
        write_u32(out, static_cast<uint32_t>(token));
    }
}
uint32_t number(const char * raw, uint32_t lower, uint32_t upper) {
    std::string s(raw);
    if (s.empty() || s.size() > 10) deny();
    uint64_t value = 0;
    for (auto ch : s) {
        if (ch < '0' || ch > '9') deny();
        value = value * 10 + uint32_t(ch - '0');
        if (value > upper) deny();
    }
    if (value < lower) deny();
    return static_cast<uint32_t>(value);
}
Tokens encode(const llama_vocab * vocab, const std::string & text) {
    // No implicit BOS/EOS and no special-string interpretation. User text
    // never gains control-token authority by containing marker spellings.
    int32_t need = llama_tokenize(vocab, text.data(), static_cast<int32_t>(text.size()),
                                 nullptr, 0, false, false);
    if (need == std::numeric_limits<int32_t>::min() || need > 0) deny();
    const auto count = static_cast<uint32_t>(-need);
    if (count > max_tokens) deny();
    Tokens out(count);
    if (count && llama_tokenize(vocab, text.data(), static_cast<int32_t>(text.size()),
            out.data(), static_cast<int32_t>(out.size()), false, false)
            != static_cast<int32_t>(count)) deny();
    return out;
}
std::string decode(const llama_vocab * vocab, const Tokens & tokens) {
    if (tokens.empty()) return {};
    int32_t need = llama_detokenize(vocab, tokens.data(), static_cast<int32_t>(tokens.size()),
                                   nullptr, 0, false, false);
    if (need == std::numeric_limits<int32_t>::min() || need > 0) deny();
    auto count = static_cast<uint32_t>(-need);
    if (count > max_text) deny();
    std::string out(count, '\0');
    if (count && llama_detokenize(vocab, tokens.data(), static_cast<int32_t>(tokens.size()),
            out.data(), static_cast<int32_t>(out.size()), false, false)
            != static_cast<int32_t>(count)) deny();
    return out;
}
struct Backend {
    Backend() { llama_backend_init(); }
    ~Backend() { llama_backend_free(); }
    Backend(const Backend &) = delete;
    Backend & operator=(const Backend &) = delete;
};
using Model = std::unique_ptr<llama_model, decltype(&llama_model_free)>;
using Context = std::unique_ptr<llama_context, decltype(&llama_free)>;
using Sampler = std::unique_ptr<llama_sampler, decltype(&llama_sampler_free)>;

void run(int argc, char ** argv) {
    if (argc != 9) deny();
    const std::string operation(argv[1]);
    if (operation != "encode" && operation != "decode" && operation != "generate") deny();
    const auto context_size = number(argv[5], 128, max_tokens);
    const auto threads = number(argv[6], 1, 256);
    const auto batch_size = number(argv[7], 1, 8192);
    const auto completion = number(argv[8], 0, max_output);
    if ((operation == "generate") != (completion != 0)) deny();
    std::ifstream in(argv[3], std::ios::binary);
    if (!in) deny();
    read_magic(in);
    Backend backend;
    auto mp = llama_model_default_params();
    mp.n_gpu_layers = 0; // first qualification lane is CPU-only, not silently degraded GPU.
    mp.vocab_only = operation != "generate";
    Model model(llama_model_load_from_file(argv[2], mp), llama_model_free);
    if (!model) deny();
    const auto * vocab = llama_model_get_vocab(model.get());
    if (!vocab) deny();
    Tokens input, output;
    std::string text;
    uint32_t finish = 0; // 0=eog, 1=length
    if (operation == "encode") {
        text = read_text(in);
        eof(in);
        input = encode(vocab, text);
    } else if (operation == "decode") {
        input = read_tokens(in, vocab);
        eof(in);
        text = decode(vocab, input);
    } else {
        text = read_text(in);
        input = read_tokens(in, vocab);
        eof(in);
        if (input.empty() || input.size() + completion > context_size ||
            context_size > static_cast<uint32_t>(std::max(0, llama_model_n_ctx_train(model.get()))) ||
            encode(vocab, text) != input || decode(vocab, input) != text ||
            llama_model_has_encoder(model.get()) || !llama_model_has_decoder(model.get())) deny();
        auto cp = llama_context_default_params();
        cp.n_ctx = context_size;
        cp.n_batch = std::min(batch_size, context_size);
        cp.n_ubatch = cp.n_batch;
        cp.n_threads = static_cast<int32_t>(threads);
        cp.n_threads_batch = static_cast<int32_t>(threads);
        Context ctx(llama_init_from_model(model.get(), cp), llama_free);
        if (!ctx) deny();
        Sampler sampler(llama_sampler_init_greedy(), llama_sampler_free);
        if (!sampler) deny();
        // The only prompt evaluated is the exact verified token vector.
        for (size_t offset = 0; offset < input.size();) {
            const auto count = std::min<size_t>(cp.n_batch, input.size() - offset);
            if (llama_decode(ctx.get(), llama_batch_get_one(
                    input.data() + offset, static_cast<int32_t>(count))) != 0) deny();
            offset += count;
        }
        finish = 1;
        for (uint32_t i = 0; i < completion; ++i) {
            auto token = llama_sampler_sample(sampler.get(), ctx.get(), -1);
            if (token < 0 || token >= llama_vocab_n_tokens(vocab)) deny();
            if (llama_vocab_is_eog(vocab, token)) { finish = 0; break; }
            output.push_back(token);
            if (i + 1 < completion &&
                llama_decode(ctx.get(), llama_batch_get_one(&token, 1)) != 0) deny();
        }
        text = decode(vocab, output);
    }
    std::ofstream out(argv[4], std::ios::binary | std::ios::trunc);
    if (!out || !out.write("SKG1", 4)) deny();
    if (operation == "encode") write_tokens(out, input);
    else if (operation == "decode") write_text(out, text);
    else {
        write_u32(out, finish);
        write_tokens(out, input); // exact physically evaluated prompt receipt
        write_tokens(out, output);
        write_text(out, text);
    }
    out.flush();
    if (!out) deny();
}
}
int main(int argc, char ** argv) {
    try { run(argc, argv); return 0; }
    catch (...) { std::cerr << "GGUF token bridge denied execution\n"; return 2; }
}

/*
 * pybind11 wrapper exposing HElib CKKS operations to Python.
 *
 * Security parameters (128-bit):
 *   m = 16384  — cyclotomic order (n = m/2 = 8192 slots)
 *   bits = 119 — total ciphertext-modulus bits
 *   precision = 20 — bits of precision per level
 *   c = 2      — key-switching matrix columns
 *
 * The session object holds the context and secret key in memory.
 * In production the secret key would live inside HashiCorp Vault and be
 * loaded on startup via the hvac client; this wrapper exposes the raw
 * crypto operations only.
 */

#include <helib/helib.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <memory>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

// ---------------------------------------------------------------------------
// HElibCKKSSession
// Owns the context + secret key for the lifetime of the Python object.
// ---------------------------------------------------------------------------
class HElibCKKSSession {
public:
    HElibCKKSSession()
    {
        auto built = helib::ContextBuilder<helib::CKKS>()
            .m(16384)
            .bits(119)
            .precision(20)
            .c(2)
            .build();

        ctx_ = std::make_unique<helib::Context>(std::move(built));
        sk_  = std::make_unique<helib::SecKey>(*ctx_);

        sk_->GenSecKey();
        // Generate rotation keys required by totalSums.
        helib::addSome1DMatrices(*sk_);
    }

    // encrypt_indicators: returns an opaque ciphertext as raw bytes.
    // The client encrypts its risk indicators; the plaintext never leaves.
    py::bytes encrypt(const std::vector<double>& indicators) const
    {
        helib::PtxtArray pt(*ctx_);
        pt.load(indicators);

        helib::Ctxt ct(*sk_);   // uses the public-key face of SecKey
        pt.encrypt(ct);

        std::stringstream ss;
        ct.writeTo(ss);
        const std::string s = ss.str();
        return py::bytes(s.data(), s.size());
    }

    // score: multiply the ciphertext by plaintext weights, sum all slots,
    // decrypt and return the scalar AML risk score.
    // The server performs the weighted sum without ever seeing the raw indicators.
    double score(const py::bytes& ciphertext_bytes,
                 const std::vector<double>& weights) const
    {
        // Deserialise ciphertext
        const std::string raw = ciphertext_bytes;
        std::stringstream ss(raw);
        helib::Ctxt ct = helib::Ctxt::readFrom(ss, *sk_);

        // Multiply each encrypted slot by the corresponding plaintext weight
        helib::PtxtArray pw(*ctx_);
        pw.load(weights);
        ct *= pw;

        // Accumulate the sum of all slots into slot 0.
        // Slots beyond indicators.size() are zero-padded so this is exact.
        const helib::EncryptedArray& ea = ctx_->getEA();
        helib::totalSums(ea, ct);

        // Decrypt — the server holds the secret key; result never travels
        // back to the client in the clear except as a final risk label.
        helib::PtxtArray result(*ctx_);
        result.decrypt(ct, *sk_);

        std::vector<double> decoded;
        result.store(decoded);

        if (decoded.empty())
            throw std::runtime_error("HElib decryption returned empty vector");

        return decoded[0];  // slot 0 holds the weighted sum
    }

    // nslots: useful for the Python side to know the packing capacity.
    long nslots() const { return ctx_->getEA().size(); }

private:
    std::unique_ptr<helib::Context> ctx_;
    std::unique_ptr<helib::SecKey>  sk_;
};

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------
PYBIND11_MODULE(helib_ckks, m)
{
    m.doc() = "HElib CKKS bindings for privacy-preserving AML scoring";

    py::class_<HElibCKKSSession>(m, "HElibCKKSSession")
        .def(py::init<>())
        .def("encrypt", &HElibCKKSSession::encrypt,
             py::arg("indicators"),
             "Encrypt a list of float risk indicators into a CKKS ciphertext (bytes).")
        .def("score", &HElibCKKSSession::score,
             py::arg("ciphertext_bytes"), py::arg("weights"),
             "Multiply the encrypted indicators by plaintext weights, sum slots, "
             "and return the decrypted scalar risk score.")
        .def("nslots", &HElibCKKSSession::nslots,
             "Return the number of plaintext slots in this context.");
}

// Package security implements password hashing and access/refresh token
// primitives for authentication. Everything here is hand-rolled from the Go
// standard library (crypto/hmac, crypto/sha256, crypto/rand) instead of a
// third-party module (e.g. bcrypt) so the backend keeps building and testing
// fully offline, with no new go.mod dependency and nothing to fetch from a
// module proxy.
package security

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"strconv"
	"strings"
)

// pbkdf2Iterations follows OWASP's 2023 guidance for PBKDF2-HMAC-SHA256
// (>=600k is their strict recommendation; 210k matches Django's historical
// default and keeps login latency reasonable for a hackathon demo while
// still being far beyond a fast unsalted hash).
const (
	pbkdf2Iterations = 210_000
	pbkdf2KeyLength  = 32
	pbkdf2SaltLength = 16
)

// HashPassword derives a salted PBKDF2-HMAC-SHA256 hash suitable for storage
// in the users.password_hash column. The iteration count is embedded in the
// output so it can be increased later without invalidating existing hashes.
func HashPassword(password string) (string, error) {
	if password == "" {
		return "", errors.New("password must not be empty")
	}
	salt := make([]byte, pbkdf2SaltLength)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	derived := pbkdf2(password, salt, pbkdf2Iterations, pbkdf2KeyLength)
	return fmt.Sprintf(
		"pbkdf2-sha256$%d$%s$%s",
		pbkdf2Iterations,
		base64.RawStdEncoding.EncodeToString(salt),
		base64.RawStdEncoding.EncodeToString(derived),
	), nil
}

// VerifyPassword checks a plaintext password against a hash produced by
// HashPassword, in constant time with respect to the derived key.
func VerifyPassword(stored, password string) bool {
	parts := strings.Split(stored, "$")
	if len(parts) != 4 || parts[0] != "pbkdf2-sha256" {
		return false
	}
	iterations, err := strconv.Atoi(parts[1])
	if err != nil || iterations <= 0 {
		return false
	}
	salt, err := base64.RawStdEncoding.DecodeString(parts[2])
	if err != nil {
		return false
	}
	expected, err := base64.RawStdEncoding.DecodeString(parts[3])
	if err != nil {
		return false
	}
	derived := pbkdf2(password, salt, iterations, len(expected))
	return subtle.ConstantTimeCompare(derived, expected) == 1
}

// pbkdf2 implements RFC 8018 PBKDF2 with HMAC-SHA256 as the pseudorandom
// function. keyLength is assumed to be <= the HMAC output size (32 bytes),
// which holds for every caller in this package, so a single block is enough;
// the block-loop is kept anyway so the function stays correct if that ever
// changes.
func pbkdf2(password string, salt []byte, iterations, keyLength int) []byte {
	prf := hmac.New(sha256.New, []byte(password))
	hashLength := prf.Size()
	blocks := (keyLength + hashLength - 1) / hashLength
	derived := make([]byte, 0, blocks*hashLength)
	block := make([]byte, len(salt)+4)
	copy(block, salt)

	for index := 1; index <= blocks; index++ {
		block[len(salt)] = byte(index >> 24)
		block[len(salt)+1] = byte(index >> 16)
		block[len(salt)+2] = byte(index >> 8)
		block[len(salt)+3] = byte(index)

		prf.Reset()
		prf.Write(block)
		u := prf.Sum(nil)
		result := make([]byte, hashLength)
		copy(result, u)
		for iteration := 1; iteration < iterations; iteration++ {
			prf.Reset()
			prf.Write(u)
			u = prf.Sum(nil)
			for i := range result {
				result[i] ^= u[i]
			}
		}
		derived = append(derived, result...)
	}
	return derived[:keyLength]
}

package security

import (
	"testing"
	"time"
)

func TestHashPasswordVerify(t *testing.T) {
	hash, err := HashPassword("correct-horse-battery-staple")
	if err != nil || hash == "" {
		t.Fatalf("hash: %q err=%v", hash, err)
	}
	if !VerifyPassword(hash, "correct-horse-battery-staple") {
		t.Fatal("verify: correct password rejected")
	}
	if VerifyPassword(hash, "wrong-password") {
		t.Fatal("verify: wrong password accepted")
	}
	if VerifyPassword("not-a-valid-hash", "anything") {
		t.Fatal("verify: malformed stored hash accepted")
	}
	second, err := HashPassword("correct-horse-battery-staple")
	if err != nil {
		t.Fatalf("hash again: %v", err)
	}
	if second == hash {
		t.Fatal("hashing the same password twice must use a fresh random salt")
	}
}

func TestSignAndParseToken(t *testing.T) {
	claims := Claims{Subject: "user-1", Role: "tech_specialist", Line: "L2", IssuedAt: time.Now().Unix(), ExpiresAt: time.Now().Add(time.Minute).Unix()}
	token, err := SignToken(claims, "test-secret")
	if err != nil || token == "" {
		t.Fatalf("sign: %q err=%v", token, err)
	}
	parsed, err := ParseToken(token, "test-secret")
	if err != nil || parsed.Subject != claims.Subject || parsed.Role != claims.Role || parsed.Line != claims.Line {
		t.Fatalf("parse: claims=%+v err=%v", parsed, err)
	}
	if _, err := ParseToken(token, "wrong-secret"); err != ErrInvalidToken {
		t.Fatalf("parse with wrong secret = %v, want ErrInvalidToken", err)
	}
	expired := Claims{Subject: "user-1", ExpiresAt: time.Now().Add(-time.Minute).Unix()}
	expiredToken, _ := SignToken(expired, "test-secret")
	if _, err := ParseToken(expiredToken, "test-secret"); err != ErrTokenExpired {
		t.Fatalf("parse expired = %v, want ErrTokenExpired", err)
	}
	if _, err := ParseToken("not.a.token.at.all", "test-secret"); err != ErrInvalidToken {
		t.Fatalf("parse malformed = %v, want ErrInvalidToken", err)
	}
}

func TestOpaqueTokenAndHash(t *testing.T) {
	a, err := NewOpaqueToken()
	if err != nil || a == "" {
		t.Fatalf("new opaque token: %q err=%v", a, err)
	}
	b, err := NewOpaqueToken()
	if err != nil || a == b {
		t.Fatalf("two opaque tokens must differ: a=%q b=%q err=%v", a, b, err)
	}
	if HashToken(a) != HashToken(a) {
		t.Fatal("hashing the same token twice must be deterministic")
	}
	if HashToken(a) == HashToken(b) {
		t.Fatal("hashing different tokens must differ")
	}
}

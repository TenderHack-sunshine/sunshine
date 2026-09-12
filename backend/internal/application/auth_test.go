package application

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
)

func newAuthService(store *fakeStore) *AuthService {
	return NewAuthService(store, AuthConfig{JWTSecret: "test-secret-at-least-32-bytes-long", AccessTokenTTL: 15 * time.Minute, RefreshTokenTTL: 30 * 24 * time.Hour})
}

func TestRegisterLoginAndTokenRoundTrip(t *testing.T) {
	store := newFakeStore()
	auth := newAuthService(store)

	result, err := auth.Register(context.Background(), " User@Example.com ", "correct-horse", "Иван Поставщик")
	if err != nil || result.AccessToken == "" || result.RefreshToken == "" {
		t.Fatalf("register: result=%+v err=%v", result, err)
	}
	if result.User.Role != domain.RoleUser || result.User.PasswordHash != "" {
		t.Fatalf("register must return a plain user with no password hash: %+v", result.User)
	}

	if _, err := auth.Register(context.Background(), "user@example.com", "another-pass", "Дубликат"); !errors.Is(err, ErrEmailTaken) {
		t.Fatalf("duplicate email = %v, want ErrEmailTaken", err)
	}

	actor, err := auth.ParseAccessToken(result.AccessToken)
	if err != nil || actor.UserID != result.User.ID || actor.Role != domain.RoleUser {
		t.Fatalf("parse access token: actor=%+v err=%v", actor, err)
	}

	if _, err := auth.Login(context.Background(), "user@example.com", "wrong-password"); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("wrong password = %v, want ErrInvalidCredentials", err)
	}
	login, err := auth.Login(context.Background(), "USER@EXAMPLE.COM", "correct-horse")
	if err != nil || login.User.ID != result.User.ID {
		t.Fatalf("login (case-insensitive email): result=%+v err=%v", login, err)
	}

	refreshed, err := auth.Refresh(context.Background(), login.RefreshToken)
	if err != nil || refreshed.AccessToken == "" {
		t.Fatalf("refresh: result=%+v err=%v", refreshed, err)
	}
	if _, err := auth.Refresh(context.Background(), login.RefreshToken); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("reusing a rotated refresh token = %v, want ErrInvalidCredentials", err)
	}

	if err := auth.Logout(context.Background(), refreshed.RefreshToken); err != nil {
		t.Fatalf("logout: %v", err)
	}
	if _, err := auth.Refresh(context.Background(), refreshed.RefreshToken); !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("refresh after logout = %v, want ErrInvalidCredentials", err)
	}
}

func TestSpecialistRegistrationRequiresApproval(t *testing.T) {
	store := newFakeStore()
	auth := newAuthService(store)
	admin := NewAdminService(store)

	if _, err := auth.RegisterSpecialist(context.Background(), "spec@example.com", "correct-horse", "Мария Спец", "L9"); !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("invalid line = %v, want ErrInvalidInput", err)
	}
	specialist, err := auth.RegisterSpecialist(context.Background(), "spec@example.com", "correct-horse", "Мария Спец", domain.SupportLineL2)
	if err != nil || specialist.SpecialistStatus != domain.SpecialistStatusPending {
		t.Fatalf("register specialist: user=%+v err=%v", specialist, err)
	}

	if _, err := auth.Login(context.Background(), "spec@example.com", "correct-horse"); !errors.Is(err, ErrPendingApproval) {
		t.Fatalf("login while pending = %v, want ErrPendingApproval", err)
	}

	plainUser := Actor{UserID: "someone-else", Role: domain.RoleUser}
	if _, err := admin.ListPendingSpecialists(context.Background(), plainUser); !errors.Is(err, ErrForbidden) {
		t.Fatalf("non-admin listing pending specialists = %v, want ErrForbidden", err)
	}

	adminActor := Actor{UserID: "admin-1", Role: domain.RoleAdmin}
	pending, err := admin.ListPendingSpecialists(context.Background(), adminActor)
	if err != nil || len(pending) != 1 || pending[0].ID != specialist.ID {
		t.Fatalf("pending specialists: list=%+v err=%v", pending, err)
	}

	if err := admin.ApproveSpecialist(context.Background(), adminActor, specialist.ID); err != nil {
		t.Fatalf("approve specialist: %v", err)
	}
	login, err := auth.Login(context.Background(), "spec@example.com", "correct-horse")
	if err != nil || login.User.Role != domain.RoleTechSpecialist || login.User.Line != domain.SupportLineL2 {
		t.Fatalf("login after approval: result=%+v err=%v", login, err)
	}

	rejected, err := auth.RegisterSpecialist(context.Background(), "rejected@example.com", "correct-horse", "Отклонённый", domain.SupportLineL1)
	if err != nil {
		t.Fatalf("register second specialist: %v", err)
	}
	if err := admin.RejectSpecialist(context.Background(), adminActor, rejected.ID); err != nil {
		t.Fatalf("reject specialist: %v", err)
	}
	if _, err := auth.Login(context.Background(), "rejected@example.com", "correct-horse"); !errors.Is(err, ErrRegistrationRejected) {
		t.Fatalf("login after rejection = %v, want ErrRegistrationRejected", err)
	}
}

func TestAdminCanGrantAndRevokeTechSpecialistDirectly(t *testing.T) {
	store := newFakeStore()
	auth := newAuthService(store)
	admin := NewAdminService(store)
	adminActor := Actor{UserID: "admin-1", Role: domain.RoleAdmin}

	registered, err := auth.Register(context.Background(), "colleague@example.com", "correct-horse", "Коллега")
	if err != nil {
		t.Fatalf("register plain user: %v", err)
	}
	plainUser := Actor{UserID: registered.User.ID, Role: domain.RoleUser}
	if err := admin.SetRole(context.Background(), plainUser, registered.User.ID, domain.RoleTechSpecialist, domain.SupportLineL3); !errors.Is(err, ErrForbidden) {
		t.Fatalf("non-admin granting a role = %v, want ErrForbidden", err)
	}

	if err := admin.SetRole(context.Background(), adminActor, registered.User.ID, domain.RoleTechSpecialist, domain.SupportLineL3); err != nil {
		t.Fatalf("grant tech_specialist: %v", err)
	}
	promoted, err := auth.Login(context.Background(), "colleague@example.com", "correct-horse")
	if err != nil || promoted.User.Role != domain.RoleTechSpecialist || promoted.User.Line != domain.SupportLineL3 {
		t.Fatalf("login after direct grant: result=%+v err=%v", promoted, err)
	}

	if err := admin.SetRole(context.Background(), adminActor, registered.User.ID, domain.RoleUser, ""); err != nil {
		t.Fatalf("revoke tech_specialist: %v", err)
	}
	demoted, err := auth.Login(context.Background(), "colleague@example.com", "correct-horse")
	if err != nil || demoted.User.Role != domain.RoleUser {
		t.Fatalf("login after revoke: result=%+v err=%v", demoted, err)
	}
}

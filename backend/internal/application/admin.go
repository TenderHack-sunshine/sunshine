package application

import (
	"context"
	"strings"

	"github.com/TenderHack-sunshine/sunshine/backend/internal/domain"
	"github.com/TenderHack-sunshine/sunshine/backend/internal/port"
)

// AdminService covers everything an admin can do to other accounts: review
// self-registered tech specialists, and grant or revoke staff status on any
// existing user directly. Every method re-checks actor.IsAdmin() itself
// (rather than trusting the HTTP layer alone) since this service is the
// actual authority boundary for role changes.
type AdminService struct {
	store port.Store
}

func NewAdminService(store port.Store) *AdminService { return &AdminService{store: store} }

func (s *AdminService) ListUsers(ctx context.Context, actor Actor) ([]domain.User, error) {
	if !actor.IsAdmin() {
		return nil, ErrForbidden
	}
	return s.store.ListUsers(ctx)
}

// ListPendingSpecialists returns self-registered tech specialists awaiting
// approval or rejection.
func (s *AdminService) ListPendingSpecialists(ctx context.Context, actor Actor) ([]domain.User, error) {
	if !actor.IsAdmin() {
		return nil, ErrForbidden
	}
	return s.store.ListSpecialistsByStatus(ctx, domain.SpecialistStatusPending)
}

func (s *AdminService) ApproveSpecialist(ctx context.Context, actor Actor, userID string) error {
	return s.decideSpecialist(ctx, actor, userID, domain.SpecialistStatusApproved)
}

func (s *AdminService) RejectSpecialist(ctx context.Context, actor Actor, userID string) error {
	return s.decideSpecialist(ctx, actor, userID, domain.SpecialistStatusRejected)
}

func (s *AdminService) decideSpecialist(ctx context.Context, actor Actor, userID string, decision domain.SpecialistStatus) error {
	if !actor.IsAdmin() {
		return ErrForbidden
	}
	if strings.TrimSpace(userID) == "" {
		return ErrInvalidInput
	}
	user, err := s.store.GetUserByID(ctx, userID)
	if err != nil {
		return err
	}
	if user.Role != domain.RoleTechSpecialist {
		return ErrInvalidState
	}
	return s.store.UpdateSpecialistStatus(ctx, userID, decision)
}

// SetRole lets an admin grant or revoke tech-specialist/admin status on any
// existing account directly, independent of the self-registration approval
// queue above (e.g. promoting a regular user who never registered as a
// specialist, or demoting a specialist/admin back to a regular user).
// Granting tech_specialist this way marks the account approved immediately.
func (s *AdminService) SetRole(ctx context.Context, actor Actor, userID string, role domain.Role, line domain.SupportLine) error {
	if !actor.IsAdmin() {
		return ErrForbidden
	}
	if strings.TrimSpace(userID) == "" {
		return ErrInvalidInput
	}
	status := domain.SpecialistStatusNone
	switch role {
	case domain.RoleUser, domain.RoleAdmin:
		line = domain.SupportLineNone
	case domain.RoleTechSpecialist:
		if !validLine(line) {
			return ErrInvalidInput
		}
		status = domain.SpecialistStatusApproved
	default:
		return ErrInvalidInput
	}
	if _, err := s.store.GetUserByID(ctx, userID); err != nil {
		return err
	}
	return s.store.UpdateUserRole(ctx, userID, role, line, status)
}

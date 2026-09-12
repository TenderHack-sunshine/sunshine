package application

import "github.com/TenderHack-sunshine/sunshine/backend/internal/domain"

// Actor is the authenticated principal performing an action, decoded from a
// verified access token by the HTTP transport layer before it reaches any
// service method. UserID is always required; Role/Line are the zero value
// for tokens issued before roles existed, which IsStaff/IsAdmin treat as
// "regular user".
type Actor struct {
	UserID string
	Role   domain.Role
	Line   domain.SupportLine
}

// IsStaff reports whether the actor may operate on escalated tickets
// (tech specialists and admins).
func (a Actor) IsStaff() bool {
	return a.Role == domain.RoleTechSpecialist || a.Role == domain.RoleAdmin
}

// IsAdmin reports whether the actor may manage other users' roles.
func (a Actor) IsAdmin() bool {
	return a.Role == domain.RoleAdmin
}

// CanHandleLine reports whether the actor may act on a ticket routed to the
// given support line (e.g. "L1"/"L2"/"L3"). Admins can handle every line; a
// tech specialist is scoped to their own assigned line. A specialist with no
// line assigned (Line == "") is treated as unscoped, so existing accounts
// created before line assignment was required are not locked out.
func (a Actor) CanHandleLine(line string) bool {
	switch a.Role {
	case domain.RoleAdmin:
		return true
	case domain.RoleTechSpecialist:
		return a.Line == "" || string(a.Line) == line
	default:
		return false
	}
}

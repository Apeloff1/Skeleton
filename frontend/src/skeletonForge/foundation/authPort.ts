/**
 * Account adapter over the existing studio auth client.
 *
 * Backend routes already in use (no new endpoints):
 *   GET  /api/auth/me
 *   POST /api/auth/login
 *   POST /api/auth/register
 *   POST /api/auth/session
 *   POST /api/auth/logout
 *
 * When `/api/auth/me` cannot be verified, that client fails closed
 * (`enforced: true`). The shell shows the unavailable sign-in state.
 */
import {
  checkMe, completeWebRedirect, googleLogin, loginEmail, logout, registerEmail,
} from '../../auth/gameforgeAuth';

export interface AuthPort {
  checkMe: typeof checkMe;
  loginEmail: typeof loginEmail;
  registerEmail: typeof registerEmail;
  googleLogin: typeof googleLogin;
  logout: typeof logout;
  completeWebRedirect: typeof completeWebRedirect;
}

export function gameforgeAuthPort(): AuthPort {
  return { checkMe, loginEmail, registerEmail, googleLogin, logout, completeWebRedirect };
}

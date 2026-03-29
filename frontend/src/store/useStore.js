import { create } from "zustand";
import client from "../api/client";

const useStore = create((set) => ({
  // ── Auth state ──────────────────────────────────────────────────────────
  token: localStorage.getItem("token"),
  user: null,
  isAuthenticated: !!localStorage.getItem("token"),

  login: async (email, password) => {
    // Backend uses OAuth2 form format for login
    const params = new URLSearchParams();
    params.append("username", email);
    params.append("password", password);
    const { data } = await client.post("/auth/login", params, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("token", data.access_token);
    set({ token: data.access_token, isAuthenticated: true });
  },

  register: async (username, email, password) => {
    await client.post("/auth/register", { username, email, password });
  },

  logout: () => {
    localStorage.removeItem("token");
    set({ token: null, user: null, isAuthenticated: false });
  },
}));

export default useStore;

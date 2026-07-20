export type ApiError = {
  code: string;
  message: string;
};

export type ApiEnvelope<T> = {
  data: T | null;
  error: ApiError | null;
};

export type TokenData = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type RefreshData = {
  access_token: string;
  expires_in: number;
};

export type UserData = {
  id: string;
  email: string;
  name: string;
  created_at: string;
};

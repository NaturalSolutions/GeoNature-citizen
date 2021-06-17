export class RegisterUser {
    username?: string;
    password?: string;
    email?: string;
    name?: string;
    surname?: string;
    avatar?: string | ArrayBuffer;
    extention?: string;
    category: string;
    organism?: string;
    function?: string;
    country: string;
    postal_code: string;
    want_newsletter: boolean;
    is_relay: boolean;
    linked_relay_id?: number;
    made_known_relay_id?: number;
    want_observation_contact: boolean;

    constructor() {
        this.category = 'individual';
        this.country = 'FR';
        this.want_newsletter = false;
        this.is_relay = false;
    }
}

export interface Relay {
    id: number;
    name: string;
}

export interface Organism {
    id_organism: number;
    name: string;
}

export interface LoginUser {
    email: string;
    password: string;
}

export interface LoginPayload {
    message: string;
    access_token?: string;
    refresh_token?: string;
    username?: string;
}

export interface LogoutPayload {
    msg: string;
}

export interface JWT {
    header: {
        typ: string;
        alg: string;
    };
    payload: JWTPayload;
}

export interface JWTPayload {
    iat: number;
    nbf: number;
    jti: string;
    exp: number;
    identity: string;
    fresh: boolean;
    type: string;
}

export interface TokenRefresh {
    access_token: string;
}

export interface UserInfo {
    message: string;
    features?: any;
}

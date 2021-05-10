import { Component, Inject, LOCALE_ID } from '@angular/core';
import { Router } from '@angular/router';
import { Subject, throwError } from 'rxjs';
import { debounceTime, catchError, map } from 'rxjs/operators';

import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';

import { RegisterUser, Relay } from '../models';
import { AuthService } from './../auth.service';
import { AppConfig } from '../../../conf/app.config';
import { UserService } from '../user-dashboard/user.service.service';

@Component({
    selector: 'register',
    templateUrl: './register.component.html',
    styleUrls: ['./register.component.css'],
})
export class RegisterComponent {
    readonly AppConfig = AppConfig;
    user: RegisterUser = new RegisterUser();
    private _error = new Subject<string>();
    private _success = new Subject<string>();
    staticAlertClosed = false;
    errorMessage: string;
    successMessage: string;
    relaysList: Array<Relay>;
    userAvatar: string | ArrayBuffer;
    categoriesEnum = Object.freeze({
        individual: 'Particulier',
        school: 'Etablissement scolaire',
        professional: 'Professionnel de la nature',
        education: 'Organisme d’éducation à l’environnement',
        other: 'Autre',
    });

    constructor(
        @Inject(LOCALE_ID) readonly localeId: string,
        private auth: AuthService,
        private userService: UserService,
        private router: Router,
        public activeModal: NgbActiveModal
    ) {}

    ngOnInit(): void {
        this.userService
            .getRelays()
            .subscribe((relayList) => (this.relaysList = relayList));
    }

    onChangeCategory(): void {
        if (this.user.category === 'individual') {
            this.user.organism = null;
            this.user.function = null;
        }
        if (
            this.user.category !== 'professional' &&
            this.user.category !== 'education'
        ) {
            this.user.is_relay = false;
        }
    }

    onRegister(): void {
        this.auth
            .register(this.user)
            .pipe(
                map((user) => {
                    if (user) {
                        const message = user.message;
                        this._success.subscribe(
                            (message) => (this.successMessage = message)
                        );
                        this._success.pipe(debounceTime(5000)).subscribe(() => {
                            this.successMessage = null;
                            this.activeModal.close();
                        });

                        this.displaySuccessMessage(message);
                        // redirect ?
                        if (this.auth.redirectUrl) {
                            this.router.navigate([this.auth.redirectUrl]);
                        }
                    }
                }),
                catchError(this.handleError)
            )
            .subscribe(
                (_data) => {},
                (errorMessage) => {
                    console.error('errorMessage', errorMessage);
                    this.errorMessage = errorMessage;
                    this.displayErrorMessage(errorMessage);
                }
            );
    }

    handleError(error) {
        let errorMessage = '';
        if (error.error instanceof ErrorEvent) {
            console.error('client-side error');
            // client-side or network error
            errorMessage = `Error: ${error.error.message}`;
        } else {
            // server-side error
            if (error.error && error.error.message) {
                // api error
                console.error('api error', error);
                errorMessage = error.error.message;
            } else {
                console.error('server-side error', error);
                errorMessage = `Error Code: ${error.status}\nMessage: ${error.message}`;
            }
        }
        return throwError(errorMessage);
    }

    displayErrorMessage(message) {
        this._error.next(message);
    }

    displaySuccessMessage(message) {
        this._success.next(message);
    }

    onUploadAvatar($event) {
        if ($event) {
            if ($event.target.files && $event.target.files[0]) {
                const reader = new FileReader();
                const file = $event.target.files[0];
                reader.readAsDataURL(file);
                reader.onload = () => {
                    this.userAvatar = reader.result;
                    this.user.avatar = this.userAvatar;
                    this.user.extention = $event.target.files[0].type
                        .split('/')
                        .pop();
                };
            }
        }
    }
}

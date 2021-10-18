import { Component, AfterViewInit } from '@angular/core';
import { FeatureCollection, Feature } from 'geojson';
import { Program } from '../programs.models';
import * as L from 'leaflet';
import { AppConfig } from '../../../conf/app.config';
import { LoginComponent } from '../../auth/login/login.component';
import { AuthService } from '../../auth/auth.service';
import { first } from 'rxjs/operators';

export abstract class ProgramBaseComponent implements AfterViewInit {
    AppConfig = AppConfig;
    fragment: string;
    coords: L.Point;
    program_id: any;
    programs: Program[];
    program: Program;
    programFeature: FeatureCollection;
    abstract flowService: any;

    protected constructor(private authService: AuthService) {}

    ngAfterViewInit(): void {
        try {
            if (this.fragment) {
                document
                    .querySelector('#' + this.fragment)
                    .scrollIntoView({ behavior: 'smooth' });
            }
        } catch (e) {
            //alert(e);
        }
    }

    ngOnDestroy(): void {
        this.flowService.closeModal();
    }

    onMapClicked(p: L.Point): void {
        this.coords = p;
        console.debug('map clicked', this.coords);
    }

    verifyProgramPrivacyAndUser() {
        if (!this.program || !this.program.is_private) {
            return;
        }

        this.authService
            .isLoggedIn()
            .pipe(first())
            .subscribe(
                function (isLoggedIn) {
                    if (isLoggedIn || !this.modalService) {
                        return;
                    }

                    if (this.authService.refreshRequest) {
                        this.authService.refreshRequest.subscribe(
                            (refreshToken) => {
                                if (refreshToken && refreshToken.access_token) {
                                    this.verifyProgramPrivacyAndUser();
                                }
                            }
                        );
                    } else {
                        const loginModalRef = this.modalService.open(
                            LoginComponent,
                            {
                                size: 'lg',
                                centered: true,
                                backdrop: 'static',
                                keyboard: false,
                            }
                        );
                        loginModalRef.componentInstance.canBeClosed = false;
                        loginModalRef.result
                            .then(this.loadData.bind(this))
                            .catch(this.loadData.bind(this));
                    }
                }.bind(this)
            );
    }

    loadData() {}
}

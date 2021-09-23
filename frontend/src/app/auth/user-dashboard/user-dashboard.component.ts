import { Component, OnInit, ViewChild } from '@angular/core';
import { Router } from '@angular/router';
import { throwError, forkJoin } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { NgbModalRef } from '@ng-bootstrap/ng-bootstrap';
import { AppConfig } from '../../../conf/app.config';
import { AuthService } from './../auth.service';
import { UserService } from './user.service.service';
import { SiteService } from '../../programs/sites/sites.service';
import { saveAs } from 'file-saver';
import * as _ from 'lodash';
import { Point, geoJSON } from 'leaflet';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { CustomFormValidator } from './customFormValidator';
import { ModalFlowService } from '../../programs/observations/modalflow/modalflow.service';
import { AreaService } from '../../programs/areas/areas.service';
import { LoginComponent } from '../login/login.component';
import { ModalsTopbarService } from '../../core/topbar/modalTopbar.service';

@Component({
    selector: 'app-user-dashboard',
    templateUrl: './user-dashboard.component.html',
    styleUrls: ['./user-dashboard.component.css'],
})
export class UserDashboardComponent implements OnInit {
    public appConfig = AppConfig;
    @ViewChild('siteDeleteModal', { static: true }) siteDeleteModal;
    modalRef: NgbModalRef;
    modalRefDel: NgbModalRef;

    username = 'not defined';
    role_id: number;
    isLoggedIn = false;
    admin = false;
    isRelay = false;
    stats: any;
    personalInfo: any = {};
    badges: any;
    main_badges: any = [];
    programs_badges: any = [];
    recognition_badges: any = [];
    AppConfig = AppConfig;
    genderType = '0';
    selectedCategory: string;

    observations: any;
    myobs: any;
    mysites: any;
    myAreas: any;
    mySpeciesSites: any;
    mySpeciesSitesObs: any;

    adminAreas: any;
    adminSpeciesSites: any;
    adminSpeciesSitesObs: any;
    adminObservers: any;

    loading = false;
    rows: any = [];
    obsToExport: any = [];
    userForm: FormGroup;
    currentUser: any;
    userAvatar: string | ArrayBuffer;
    extentionFile: any;
    newAvatar: string | ArrayBuffer;
    idObsToDelete: number;
    idSiteToDelete: number;
    tab = 'observations';
    selectedAreasTab = 'areas';
    previousObsPageData;
    relaysList = [];

    constructor(
        private auth: AuthService,
        private userService: UserService,
        private router: Router,
        private modalService: ModalsTopbarService,
        private flowService: ModalFlowService,
        private formBuilder: FormBuilder,
        public siteService: SiteService,
        public areaService: AreaService
    ) {}

    ngOnInit(): void {
        this.verifyUser();

        const tab = localStorage.getItem('selectedAreasTab');
        this.selectedAreasTab = tab ? tab : 'areas';

        this.areaService.areaEdited.subscribe(this.getData.bind(this));
        this.areaService.areaDeleted.subscribe(this.getData.bind(this));
        this.areaService.speciesSiteEdited.subscribe(this.getData.bind(this));
        this.areaService.speciesSiteDeleted.subscribe(this.getData.bind(this));
        this.userService.userEdited.subscribe(this.getData.bind(this));
        this.areaService.speciesSiteObsEdited.subscribe(
            this.refreshAdminObservationsList.bind(this)
        );
        this.areaService.speciesSiteObsDeleted.subscribe(
            this.refreshAdminObservationsList.bind(this)
        );
    }

    onChangeCategory(): void {
        this.selectedCategory = this.userForm.value.category;
        if (this.selectedCategory === 'individual') {
            this.userForm.get('organism').setValue(null);
        }
    }

    verifyUser() {
        const access_token = localStorage.getItem('access_token');
        if (!access_token) {
            this.openLoginModal();
            return;
        }
        this.auth
            .ensureAuthorized()
            .pipe(
                tap((user) => {
                    if (
                        user &&
                        user['features'] &&
                        user['features']['id_role']
                    ) {
                        this.isLoggedIn = true;
                        this.username = user['features']['username'];
                        this.stats = user['features']['stats'];
                        this.role_id = user['features']['id_role'];
                        this.admin = user['features']['admin'];
                        this.isRelay = user['features']['is_relay'];
                        this.userService.role_id = this.role_id;
                        this.userService.admin = this.admin;
                        if (user['features']['avatar'])
                            this.userAvatar =
                                this.appConfig.API_ENDPOINT +
                                '/media/' +
                                user['features']['avatar'];
                        // FIXME: source backend conf
                        this.getData();
                        this.flowService
                            .getModalCloseSatus()
                            .subscribe((status) => {
                                if (status === 'updateObs') this.getData();
                            });
                        this.siteService.siteEdited.subscribe(() => {
                            this.mysites = null;
                            this.getData();
                        });
                        this.modalService.close();
                    }
                }),
                catchError((err) => {
                    this.openLoginModal();
                    return throwError(err);
                })
            )
            .subscribe((user) => {
                this.currentUser = user;
            });
        this.siteService.deleteSite.subscribe(($event) => {
            this.openSiteDeleteModal(this.siteDeleteModal, $event);
        });
    }

    openLoginModal() {
        const loginModalRef = this.modalService.open(LoginComponent, {
            size: 'lg',
            centered: true,
            backdrop: 'static',
            keyboard: false,
        });
        loginModalRef.componentInstance.canBeClosed = false;
        loginModalRef.result
            .then(
                function (result) {
                    if (result.componentInstance) {
                        result.result.then(
                            function (result) {
                                if (result === 'registered') {
                                    this.verifyUser();
                                }
                            }.bind(this)
                        );
                        return;
                    }
                    this.verifyUser();
                }.bind(this)
            )
            .catch(this.verifyUser.bind(this));
    }

    getData() {
        this.loading = true;

        this.getAdminData();

        const data = [];
        this.rows = [];
        this.obsToExport = [];
        this.observations = null;
        this.badges = null;
        this.main_badges = [];
        this.programs_badges = [];
        this.recognition_badges = [];
        const badgeCategories = this.userService.getBadgeCategories(
            this.role_id
        );
        const userObservations = this.userService.getObservationsByUserId(
            this.role_id
        );
        const userSites = this.userService.getSitesByUserId(this.role_id);

        const userAreas = this.userService.getCurrentUserAreas();
        const userSpeciesSites = this.userService.getCurrentUserSpeciesSites();
        const userSpeciesSitesObs =
            this.userService.getCurrentUserSpeciesSitesObs();

        data.push(userObservations);
        data.push(userSites);
        data.push(userAreas);
        data.push(userSpeciesSites);
        data.push(userSpeciesSitesObs);
        if (AppConfig['REWARDS']) {
            data.push(badgeCategories);
        }
        forkJoin(data).subscribe((data: any) => {
            this.loading = false;

            if (data.length <= 1) {
                this.observations = data[0].features;
                this.observations.forEach((obs) => {
                    const coords: Point = new Point(
                        obs.geometry.coordinates[0],
                        obs.geometry.coordinates[1]
                    );
                    obs.coords = coords;
                    this.rowData(obs, coords);
                    this.obsExport(obs);
                });
                return;
            }

            this.myobs = data[0];
            this.mysites = data[1];
            this.myAreas = data[2];

            if (!this.myobs.count) {
                if (this.mysites.count) {
                    this.tab = 'sites';
                } else if (this.myAreas.count) {
                    this.tab = 'areas';
                }
            }

            this.tab = 'admin';

            this.mySpeciesSites = data[3];
            this.mySpeciesSitesObs = data[4];
            if (AppConfig['REWARDS']) {
                this.badges = data[5];
                localStorage.setItem('badges', JSON.stringify(this.badges));
                console.log('badges', this.badges);
                if (this.badges.length > 0) {
                    this.badges.forEach((badge) => {
                        if (
                            badge.type == 'all_attendance' ||
                            badge.type == 'seniority'
                        )
                            this.main_badges.push(badge);
                        if (badge.type == 'program_attendance')
                            this.programs_badges.push(badge);
                        if (badge.type == 'recognition')
                            this.recognition_badges.push(badge);
                    });
                }
            }
            this.observations = this.myobs.features;
            this.observations.forEach((obs) => {
                const coords: Point = new Point(
                    obs.geometry.coordinates[0],
                    obs.geometry.coordinates[1]
                );
                obs.properties.coords = coords; // for use in user obs component
                this.rowData(obs, coords);
                this.obsExport(obs);
            });
            this.mysites.features.forEach((site) => {
                const coords: Point = new Point(
                    site.geometry.coordinates[0],
                    site.geometry.coordinates[1]
                );
                site.properties.coords = coords;
            });
            this.myAreas.features.forEach((area) => {
                const coords: Point = new Point(
                    area.geometry.coordinates[0],
                    area.geometry.coordinates[1]
                );
                area.properties.coords = coords;
            });
        });
    }

    getAdminData() {
        if (!this.admin && !this.isRelay) {
            return;
        }
        const adminData = [];
        const adminAreas = this.userService.getAdminAreas();
        const adminSpeciesSites = this.userService.getAdminSpeciesSites();
        const adminObservers = this.userService.getAdminObservers();

        adminData.push(adminAreas);
        adminData.push(adminSpeciesSites);
        adminData.push(adminObservers);

        forkJoin(adminData).subscribe((data: any) => {
            if (data.length > 1) {
                this.adminAreas = data[0];
                this.adminSpeciesSites = data[1];
                this.adminObservers = data[2];

                this.adminAreas.features.forEach((area) => {
                    const areaCenter = geoJSON(area).getBounds().getCenter();
                    area.properties.coords = new Point(
                        areaCenter.lng,
                        areaCenter.lat
                    );
                });

                this.adminSpeciesSites.features.forEach((site) => {
                    const coords: Point = new Point(
                        site.geometry.coordinates[0],
                        site.geometry.coordinates[1]
                    );
                    site.properties.coords = coords;
                });
            }
        });
    }

    refreshAdminObservationsList(event = null) {
        let data = { page: 0, pageSize: 0, id_program: 0 };
        if (event) {
            try {
                data = JSON.parse(event);
                this.previousObsPageData = data;
            } catch (e) {
                console.log('non valid json data', event, e);
            }
        } else if (this.previousObsPageData) {
            data = this.previousObsPageData;
        }
        const adminSpeciesSitesObs = this.userService.getAdminSpeciesSitesObs(
            data.page,
            data.pageSize,
            data.id_program
        );
        adminSpeciesSitesObs.subscribe((data) => {
            this.adminSpeciesSitesObs = data;
        });
    }

    rowData(obs, coords) {
        this.rows.push({
            media_url:
                obs.properties.images && !!obs.properties.images.length
                    ? AppConfig.API_ENDPOINT +
                      '/media/' +
                      obs.properties.images[0]
                    : obs.properties.image
                    ? obs.properties.image
                    : obs.properties.medias && !!obs.properties.medias.length
                    ? AppConfig.API_TAXHUB +
                      '/tmedias/thumbnail/' +
                      obs.properties.medias[0].id_media +
                      '?h=80&v=80'
                    : 'assets/default_image.png',
            taxref: obs.properties.taxref,
            date: obs.properties.date,
            municipality: obs.properties.municipality
                ? obs.properties.municipality.name
                : null,
            program_id: obs.properties.id_program,
            program: obs.properties.program_title,
            count: obs.properties.count,
            comment: obs.properties.comment,
            id_observation: obs.properties.id_observation,
            taxon: {
                media: obs.properties.media,
                taxref: obs.properties.taxref,
            },
            coords: coords,
            json_data: obs.properties.json_data,
        });
    }

    obsExport(obs) {
        this.obsToExport.push({
            id_observation: obs.properties.id_observation,
            date: obs.properties.date,
            programme: obs.properties.program_title,
            denombrement: obs.properties.count,
            commentaire: obs.properties.comment,
            commune: obs.properties.municipality
                ? obs.properties.municipality.name
                : null,
            cd_nom: obs.properties.taxref.cd_nom,
            espece: obs.properties.taxref.nom_vern,
            'nom complet': obs.properties.taxref.nom_complet,
            coordonnee_x: obs.geometry.coordinates[0],
            coordonnee_y: obs.geometry.coordinates[1],
            ...obs.properties.json_data,
        });
    }

    onDeletePersonalData() {
        window.open(
            'mailto:web@creamontblanc.org?subject=Suppression de mon compte'
        );
    }

    onExportPersonalData() {
        this.userService.getPersonalInfo().subscribe((data) => {
            const blob = new Blob([JSON.stringify(data)], {
                type: 'text/plain;charset=utf-8',
            });
            saveAs(blob, 'mydata.txt');
            //alert(JSON.stringify(data));
            // TODO: data format: csv, geojson ? Link observations and associated medias ?
        });
    }

    onExportObservations() {
        const all_json_data_keys = new Set();
        this.observations.forEach((o) => {
            if (o.properties.json_data) {
                Object.keys(o.properties.json_data).forEach((k) => {
                    all_json_data_keys.add(k);
                });
            }
        });
        const csv_str = this.userService.ConvertToCSV(this.obsToExport, [
            'id_observation',
            'espece',
            'cd_nom',
            'nom complet',
            'date',
            'programme',
            'denombrement',
            'commentaire',
            'commune',
            'coordonnee_x',
            'coordonnee_y',
            ...Array.from(all_json_data_keys),
        ]);
        const blob = new Blob([csv_str], { type: 'text/csv' });
        saveAs(blob, 'mydata.csv');
    }

    onExportSites() {
        this.userService.exportSites(this.role_id);
    }

    onExportAreas(allData = false) {
        this.userService.exportAreas(this.role_id, allData);
    }

    onEditInfos(content): void {
        this.loading = true;

        this.userService
            .getRelays()
            .subscribe((relayList) => (this.relaysList = relayList));

        this.userService.getPersonalInfo().subscribe((data) => {
            this.loading = false;
            this.personalInfo = data;
            this.initForm();
            this.modalRef = this.modalService.open(content, {
                size: 'lg',
                windowClass: 'add-obs-modal',
                centered: true,
            });
        });
    }

    onUpdatePersonalData(userForm) {
        userForm = _.omitBy(userForm, _.isNil);
        delete userForm.username;
        if (this.newAvatar && this.extentionFile) {
            userForm.avatar = this.userAvatar;
            userForm.extention = this.extentionFile;
        }

        if (userForm.linked_relay_id == 0) {
            userForm.linked_relay_id = null;
        }

        userForm.want_newsletter = userForm.want_newsletter ? 1 : 0;
        userForm.want_observation_contact = userForm.want_observation_contact
            ? 1
            : 0;

        this.loading = true;
        this.userService.updatePersonalData(userForm).subscribe((user: any) => {
            this.loading = false;
            localStorage.setItem('userAvatar', user.features.avatar);
            this.modalRef.close();
        });
    }

    onUploadAvatar($event) {
        if ($event) {
            if ($event.target.files && $event.target.files[0]) {
                const file = $event.target.files[0];
                const img = document.createElement('img');
                img.onload = (event) => {
                    let newImage = null;
                    if (event.target) {
                        newImage = event.target;
                    } else if (!event['path'] || !event['path'].length) {
                        newImage = event['path'][0];
                    }
                    if (!newImage) {
                        console.error('No image found on this navigator');
                        return;
                    }
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');

                    let resizeTimeNumber = 1;
                    const maxHeightRatio =
                        newImage.height / AppConfig.imageUpload.maxHeight;
                    if (maxHeightRatio > 1) {
                        resizeTimeNumber = maxHeightRatio;
                    }
                    const maxWidthRatio =
                        newImage.width / AppConfig.imageUpload.maxWidth;
                    if (maxWidthRatio > 1 && maxWidthRatio > maxHeightRatio) {
                        resizeTimeNumber = maxWidthRatio;
                    }

                    canvas.width = newImage.width / resizeTimeNumber;
                    canvas.height = newImage.height / resizeTimeNumber;

                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                    const resizedImage = canvas.toDataURL(
                        'image/jpeg',
                        AppConfig.imageUpload.quality
                    );

                    console.log('resized image', resizedImage);

                    this.userAvatar = resizedImage;
                    this.newAvatar = resizedImage;
                    this.extentionFile = 'jpeg';
                };
                img.src = window.URL.createObjectURL(file);
            }
        }
    }

    initForm() {
        const dbGender = this.personalInfo.features.gender;
        this.selectedCategory = this.personalInfo.features.category;
        this.genderType = dbGender === 'm' ? '0' : dbGender === 'f' ? '1' : '2';
        this.userForm = this.formBuilder.group(
            {
                username: [
                    {
                        value: this.personalInfo.features.username,
                        disabled: true,
                    },
                ],
                email: [
                    this.personalInfo.features.email,
                    [
                        Validators.required,
                        Validators.pattern(
                            "^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
                        ),
                    ],
                ],
                category: [this.personalInfo.features.category],
                organism: [this.personalInfo.features.organism],
                function: [this.personalInfo.features.function],
                country: [this.personalInfo.features.country],
                postal_code: [this.personalInfo.features.postal_code],
                birth_year: [this.personalInfo.features.birth_year],
                gender: [dbGender],
                comments: [this.personalInfo.features.comments],
                linked_relay_id: [
                    this.personalInfo.features.linked_relay_id
                        ? this.personalInfo.features.linked_relay_id
                        : 0,
                ],
                want_newsletter: [this.personalInfo.features.want_newsletter],
                want_observation_contact: [
                    this.personalInfo.features.want_observation_contact,
                ],
                newPassword: [null],
                confirmPassword: [null],
            },
            {
                validator: CustomFormValidator.MatchPassword,
            }
        );
    }

    openDeleteModal(deleteModal: any, idObs: number) {
        this.idObsToDelete = idObs;
        this.modalRefDel = this.modalService.open(deleteModal, {
            windowClass: 'delete-modal',
            centered: true,
        });
    }

    onCancelDelete() {
        this.modalRefDel.close();
    }

    onDeleteObs() {
        this.userService
            .deleteObsservation(this.idObsToDelete)
            .subscribe(() => {
                this.modalRefDel.close();
                this.getData();
                this.idObsToDelete = null;
            });
    }

    openSiteDeleteModal(deleteModal: any, idSite: number) {
        this.idSiteToDelete = idSite;
        this.modalRefDel = this.modalService.open(deleteModal, {
            windowClass: 'delete-modal',
            centered: true,
        });
    }

    onSiteCancelDelete() {
        this.modalRefDel.close();
    }

    onDeleteSite() {
        this.userService.deleteSite(this.idSiteToDelete).subscribe(() => {
            this.modalRefDel.close();
            this.mysites = null;
            this.getData();
            this.idSiteToDelete = null;
        });
    }

    onChangeGenreType(event): void {
        let value = '';
        this.genderType = event.target.value;
        if (this.genderType === '0') {
            value = 'm';
        } else if (this.genderType === '1') {
            value = 'f';
        }
        this.userForm.get('gender').setValue(value);
    }

    selectAreasTab(tab) {
        this.selectedAreasTab = tab;
        localStorage.setItem('selectedAreasTab', tab);
    }

    ngOnDestroy(): void {
        if (this.modalRef) this.modalRef.close();
        if (this.modalRefDel) this.modalRefDel.close();
        this.flowService.setModalCloseSatus(null);
    }
}

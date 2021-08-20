import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AppConfig } from '../../../conf/app.config';
import { catchError } from 'rxjs/operators';
import { throwError } from 'rxjs';
import { saveAs } from 'file-saver';

@Injectable({
    providedIn: 'root',
})
export class UserService {
    role_id: number;
    private headers: HttpHeaders = new HttpHeaders({
        'Content-Type': 'application/json',
    });

    constructor(private http: HttpClient) {}

    getPersonalInfo() {
        let url = `${AppConfig.API_ENDPOINT}/user/info`;
        return this.http.get(url, { headers: this.headers });
    }

    getBadgeCategories(userId: number) {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/rewards/${userId}`
        );
    }

    updatePersonalData(personalInfo) {
        console.log('up', personalInfo);

        return this.http
            .patch(`${AppConfig.API_ENDPOINT}/user/info`, personalInfo, {
                headers: this.headers,
            })
            .pipe(
                catchError((error) => {
                    return throwError(error);
                })
            );
    }

    getObservationsByUserId(userId: number) {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/observations/users/${userId}`
        );
    }

    getSitesByUserId(userId: number) {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/sites/users/${userId}`
        );
    }

    getCurrentUserAreas() {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/areas/current_user`
        );
    }

    getCurrentUserSpeciesSites() {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/areas/species_sites/current_user`
        );
    }

    getCurrentUserSpeciesSitesObs() {
        return this.http.get<Object>(
            `${AppConfig.API_ENDPOINT}/areas/observations/current_user`
        );
    }

    deleteObsservation(idObs: any) {
        return this.http.delete<Object>(
            `${AppConfig.API_ENDPOINT}/observations/${idObs}`
        );
    }

    deleteSite(idSite: any) {
        return this.http.delete<Object>(
            `${AppConfig.API_ENDPOINT}/sites/${idSite}`
        );
    }

    ConvertToCSV(objArray, headerList) {
        let array =
            typeof objArray != 'object' ? JSON.parse(objArray) : objArray;
        let str = '';
        let row = '';
        for (let index in headerList) {
            row += headerList[index] + ';';
        }
        row = row.slice(0, -1);
        str += row + '\r\n';
        for (let i = 0; i < array.length; i++) {
            let line = '';
            for (let index in headerList) {
                let head = headerList[index];
                line += ';' + (array[i][head] || '');
            }
            line = line.slice(1);
            str += line + '\r\n';
        }
        return str;
    }

    downloadFile(route: string, filename: string = null): void {
        const baseUrl = AppConfig.API_ENDPOINT;
        const token = 'my JWT';
        const headers = new HttpHeaders().set(
            'authorization',
            'Bearer ' + token
        );
        this.http
            .get(baseUrl + route, { headers, responseType: 'blob' as 'json' })
            .subscribe((response: any) => {
                let dataType = response.type;
                let binaryData = [];
                binaryData.push(response);
                saveAs(new Blob(binaryData, { type: dataType }), filename);
            });
    }

    exportSites(userId: number) {
        this.downloadFile(`/sites/export/${userId}`, 'gnc_export_sites.xls');
    }
}

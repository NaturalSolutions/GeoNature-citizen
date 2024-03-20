import { Component, AfterViewInit, ViewEncapsulation } from '@angular/core';
import { GncProgramsService } from '../../../api/gnc-programs.service';
import { ActivatedRoute } from '@angular/router';
import * as L from 'leaflet';
import { MainConfig } from '../../../../conf/main.config';
import { HttpClient } from '@angular/common/http';
import {
    BaseDetailComponent,
    markerIcon,
} from '../../base/detail/detail.component';

declare let $: any;

@Component({
    selector: 'app-obs-detail',
    templateUrl: '../../base/detail/detail.component.html',
    styleUrls: [
        './../../observations/obs.component.css', // for form modal only
        '../../base/detail/detail.component.css',
    ],
    encapsulation: ViewEncapsulation.None,
})
export class ObsDetailComponent
    extends BaseDetailComponent
    implements AfterViewInit {
    constructor(
        private http: HttpClient,
        private route: ActivatedRoute,
        private programService: GncProgramsService
    ) {
        super();
        this.route.params.subscribe((params) => {
            this.obs_id = params['obs_id'];
            this.program_id = params['program_id'];
        });
        this.module = 'observations';
    }

    ngAfterViewInit() {
        this.programService.getObsDetails(this.obs_id).subscribe((obs) => {
            this.obs = obs['features'][0];
            this.photos = [];
            this.photos = this.obs.properties.photos;
            for (var i = 0; i < this.photos.length; i++) {
                this.photos[i]['url'] =
                    MainConfig.API_ENDPOINT + this.photos[i]['url'];
            }

            // setup map
            const map = L.map('map');
            L.tileLayer('//{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: 'OpenStreetMap',
            }).addTo(map);

            let coord = this.obs.geometry.coordinates;
            let latLng = L.latLng(coord[1], coord[0]);
            map.setView(latLng, 13);

            L.marker(latLng, { icon: markerIcon }).addTo(map);

            // prepare data
            if (this.obs.properties.json_data) {
                const data = this.obs.properties.json_data;
                this.loadJsonSchema().subscribe((customform: any) => {
                    const schema = customform.json_schema.schema.properties;
                    this.attributes = this.formatData(data, schema);
                });
            }
        });
    }

    loadJsonSchema() {
        return this.http.get(
            `${this.URL}/programs/${this.program_id}/customform/`
        );
    }

    formatData(data: any, schema: any): any[] {
        const formattedData: any[] = [];
        this.flattenObject(data, schema, formattedData);
        return formattedData;
    }

    flattenObject(obj: any, schema: any, formattedData: any[]): void {
        for (const key in obj) {
            if (!obj.hasOwnProperty(key)) continue;

            const value = obj[key];
            const propSchema = schema[key];

            if (Array.isArray(value)) {
                const isArrayType = propSchema.type == 'array';
                const listFormattedString = [];
                value.forEach((item: any, index) => {
                    const schema_nested = propSchema.items.properties;
                    const formattedStrings = this.formatArrayItem(
                        item,
                        schema_nested
                    );
                    listFormattedString.push(formattedStrings);
                });
                formattedData.push({
                    name: propSchema.title,
                    value: listFormattedString,
                    showDetails: isArrayType,
                    type: propSchema.type,
                });
            } else if (typeof value === 'object') {
                this.flattenObject(
                    value,
                    propSchema.items.properties,
                    formattedData
                );
            } else {
                const propName = propSchema.title;
                const isArrayType = propSchema.type == 'array';
                formattedData.push({
                    name: propName,
                    value: value.toString(),
                    showDetails: isArrayType,
                    type: propSchema.type,
                });
            }
        }
    }

    formatArrayItem(item: any, schema: any): string {
        let formattedString = '';
        for (const k in item) {
            const nestedValue = item[k];
            const nestedSchema = schema[k];
            formattedString += `<p>${
                nestedSchema.title
            }: ${nestedValue.toString()}</p>`;
        }
        return formattedString;
    }
}

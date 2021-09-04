import {
    Component,
    OnChanges,
    Input,
    EventEmitter,
    Output,
} from '@angular/core';

import { FeatureCollection, Feature } from 'geojson';
import { AreaModalFlowService } from '../../modalflow/modalflow.service';
import { UserService } from '../../../../auth/user-dashboard/user.service.service';
import { AreaService } from '../../areas.service';
import { AppConfig } from '../../../../../conf/app.config';
import * as L from 'leaflet';

@Component({
    selector: 'app-areas-list',
    templateUrl: './list.component.html',
    styleUrls: ['./list.component.css'],
})
export class AreasListComponent implements OnChanges {
    @Input('areas') areasCollection: FeatureCollection;
    @Input('userDashboard') userDashboard = false;
    @Input('program_id') program_id: number;
    @Input('displayForm') display_form: boolean;
    @Output('areaSelect')
    areaSelect: EventEmitter<Feature> = new EventEmitter();
    municipalities: string[] = [];
    areas = [];
    taxa: any[] = [];
    apiEndpoint = AppConfig.API_ENDPOINT;

    constructor(
        public flowService: AreaModalFlowService,
        private userService: UserService,
        private areaService: AreaService
    ) {}

    ngOnChanges() {
        if (this.areasCollection) {
            this.areas = this.areasCollection['features'];

            this.areas.forEach((area) => {
                const areaCenter = L.geoJSON(area).getBounds().getCenter();
                area.properties.coords = new L.Point(
                    areaCenter.lng,
                    areaCenter.lat
                );
            });

            this.municipalities = this.areasCollection.features
                .map((features) => features.properties)
                .map((property) => property.municipality)
                .filter((municipality) =>
                    municipality != null ? <string>municipality : ''
                )
                .filter((v, i, a) => a.indexOf(v) === i);
        }
    }
    onAddSpeciesSiteClick(area_id) {
        this.flowService.addAreaSpeciesSite(area_id);
    }

    onAreaClick(e): void {
        this.areaSelect.emit(e);
    }
}

import {
    Component,
    OnChanges,
    Input,
    // HostListener,
    ChangeDetectorRef,
    SimpleChanges,
    Output,
    EventEmitter,
} from '@angular/core';
import { Router } from '@angular/router';
import { BehaviorSubject, merge } from 'rxjs';
import { pluck, share } from 'rxjs/operators';

import { FeatureCollection, Feature } from 'geojson';

import { AppConfig } from '../../../../conf/app.config';
import {
    TaxonomyList,
    TaxonomyListItem,
    ObservationFeature,
} from '../observation.model';

@Component({
    selector: 'app-obs-list',
    templateUrl: './list.component.html',
    styleUrls: ['./list.component.css'],
})
export class ObsListComponent implements OnChanges {
    @Input('observations') observations: FeatureCollection;
    @Input('taxa') surveySpecies: TaxonomyList;
    @Input('displayOwnerActions') displayOwnerActions: boolean = false;
    @Input('displayForm') display_form: boolean;
    @Output('obsSelect') obsSelect: EventEmitter<Feature> = new EventEmitter();
    @Output() deleteObs = new EventEmitter();
    municipalities: any[];
    observationList: Feature[] = [];
    program_id: number;
    taxa: any[];
    public appConfig = AppConfig;
    selectedTaxon: TaxonomyListItem = null;
    selectedMunicipality: any = null;
    changes$ = new BehaviorSubject<SimpleChanges>(null);
    observations$ = new BehaviorSubject<Feature[]>(null);
    features$ = merge(
        this.observations$,
        this.changes$.pipe(
            pluck('observations', 'currentValue', 'features'),
            share()
        )
    );

    constructor(private cd: ChangeDetectorRef, public router: Router) {}

    ngOnChanges(changes: SimpleChanges) {
        this.changes$.next(changes);

        if (this.observations) {
            this.observationList = this.observations['features'];
            this.observations$.next(this.observations['features']);
            this.municipalities = this.observations.features
                .map((features) => features.properties)
                .map((property) => property.municipality)
                .map((municipality) => {
                    return municipality.name;
                })
                .filter((item, pos, self) => {
                    return self.indexOf(item) === pos;
                });
        }
    }

    // @HostListener("document:NewObservationEvent", ["$event"])
    // public newObservationEventHandler(e: CustomEvent) {
    // }

    onFilterChange(): void {
        let filters: { taxon: string; municipality: string } = {
            taxon: null,
            municipality: null,
        };
        // WARNING: map.observations is connected to this.observationList
        this.observationList = this.observations['features'].filter((obs) => {
            let results: boolean[] = [];
            if (this.selectedMunicipality) {
                results.push(
                    obs.properties.municipality.name ==
                        this.selectedMunicipality
                );
                filters.municipality = this.selectedMunicipality;
            }
            if (this.selectedTaxon) {
                results.push(
                    obs.properties.cd_nom == this.selectedTaxon.taxref['cd_nom']
                );
                filters.taxon = this.selectedTaxon.taxref['cd_nom'];
            }
            return results.indexOf(false) < 0;
        });
        this.observations$.next(this.observationList);

        if (filters.taxon || filters.municipality) {
            const event: CustomEvent = new CustomEvent(
                'ObservationFilterEvent',
                {
                    bubbles: true,
                    cancelable: true,
                    detail: filters,
                }
            );
            document.dispatchEvent(event);
        }
    }

    onObsClick(e): void {
        this.obsSelect.emit(e);
    }

    trackByObs(index: number, obs: ObservationFeature): number {
        return obs.properties.id_observation;
    }
}

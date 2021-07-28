import {
    Component,
    Input,
    ViewChild,
} from '@angular/core';

import { IFlowComponent } from '../../../../observations/modalflow/flow/flow';
import { AreaVisitFormComponent } from '../../../form/form.component';

@Component({
    templateUrl: './visit_step.component.html',
    styleUrls: ['./visit_step.component.css'],
    // encapsulation: ViewEncapsulation.None
})
export class VisitStepComponent implements IFlowComponent {
    @Input() data: any;
    @ViewChild(AreaVisitFormComponent, { static: true })
    form: AreaVisitFormComponent;

    committed() {
        this.form.onFormSubmit();
        console.debug('committed action > data:', this.data);
        // this.data.next();
        this.data.service.close(null);
    }

    closeModal() {
        this.data.service.closeModal();
    }
}

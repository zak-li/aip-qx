import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { AgentPageComponent } from './pages/agent-page/agent-page.component';

const routes: Routes = [
  { path: '', redirectTo: 'agent', pathMatch: 'full' },
  { path: 'agent', component: AgentPageComponent },
  { path: '**', redirectTo: 'agent' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule {}

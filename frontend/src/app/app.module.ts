import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';

import { ToastComponent } from './components/toast/toast.component';
import { StatusLineComponent } from './components/status-line/status-line.component';
import { LoginFormComponent } from './components/login-form/login-form.component';
import { WelcomeComponent } from './components/welcome/welcome.component';
import { ChartBlockComponent } from './components/chart-block/chart-block.component';
import { MermaidBlockComponent } from './components/mermaid-block/mermaid-block.component';
import { MsgMetaComponent } from './components/msg-meta/msg-meta.component';
import { MessageListComponent } from './components/message-list/message-list.component';
import { OptionsPanelComponent } from './components/options-panel/options-panel.component';
import { SuggestionsComponent } from './components/suggestions/suggestions.component';
import { InputBarComponent } from './components/input-bar/input-bar.component';
import { CommandPaletteComponent } from './components/command-palette/command-palette.component';
import { EntityPanelComponent } from './components/entity-panel/entity-panel.component';
import { AgentPageComponent } from './pages/agent-page/agent-page.component';

@NgModule({
  declarations: [
    AppComponent,
    ToastComponent,
    StatusLineComponent,
    LoginFormComponent,
    WelcomeComponent,
    ChartBlockComponent,
    MermaidBlockComponent,
    MsgMetaComponent,
    MessageListComponent,
    OptionsPanelComponent,
    SuggestionsComponent,
    InputBarComponent,
    CommandPaletteComponent,
    EntityPanelComponent,
    AgentPageComponent,
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    FormsModule,
    HttpClientModule,
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule {}

import asyncio 
import random 
import time 

async def simulate_failed_request (req_id :int ,use_jitter :bool ):
    base_delay =1.0 
    jitter_amount =0.2 if use_jitter else 0.0 

    wait_delay =base_delay +random .uniform (0 ,jitter_amount )

    await asyncio .sleep (wait_delay )

    print (f"   [Requête {req_id :02d}] ➔ Frappe le serveur à +{wait_delay :.3f} secondes")

async def run_simulation (use_jitter :bool ):
    etat ="AVEC JITTER (Protection Activée)"if use_jitter else "SANS JITTER (Troupeau Tonitruant)"
    print (f"\n=== Lancement de 10 requêtes concurrentes {etat } ===")

    start_time =time .time ()
    tasks =[simulate_failed_request (i ,use_jitter )for i in range (1 ,11 )]
    await asyncio .gather (*tasks )

    print (f"-> Temps total écoulé : {time .time ()-start_time :.3f}s")

async def main ():
    print ("DÉMONSTRATION VISUELLE DU PROBLÈME DU THUNDERING HERD\n")

    await run_simulation (use_jitter =False )
    print ("   ! DANGER : Toutes les requêtes tapent le processeur EXACTEMENT à la même milliseconde !")

    await asyncio .sleep (1 )

    await run_simulation (use_jitter =True )
    print ("   ✓ SÉCURISÉ : Les requêtes sont diluées sur une plage de 200ms. La charge serveur est lissée.")

if __name__ =="__main__":
    asyncio .run (main ())

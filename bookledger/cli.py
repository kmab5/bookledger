from pathlib import Path
from typing import Optional
import typer
from .core import connect, scan
from .export import export_csv, export_json
app=typer.Typer(help='Metadata-only ebook catalog and reading log (no file modifications).',no_args_is_help=True)
DEFAULT=Path.home()/'.bookledger'/'library.sqlite3'
def database(path:Path):
    path=path.expanduser();path.parent.mkdir(parents=True,exist_ok=True);return connect(path)
@app.command()
def scan_folder(folder:Path=typer.Argument(...,help='Folder to recursively index'),db:Path=typer.Option(DEFAULT,'--db'),online:bool=typer.Option(True,'--online/--offline',help='Automatically consult Open Library')):
    """Scan a directory, read metadata, and enrich matching records."""
    import time
    started=time.monotonic()
    typer.echo(f'Scanning: {folder.expanduser().resolve()}')
    typer.echo(f'Mode: {"online enrichment" if online else "offline"} | Database: {db.expanduser()}')
    def report(event):
        kind=event['event']
        if kind=='directory':
            typer.echo(f'  Directory: {event["path"]}', err=False)
        elif kind=='file_start':
            typer.echo(f'  [{event["processed"]}] {event["path"]}', err=False)
        elif kind=='stage':
            typer.echo(f'      {event["stage"]}...', err=False)
        elif kind=='file_done':
            extra=f' (warning: {event["warning"]})' if event.get('warning') else ''
            typer.echo(f'      -> {event["outcome"]}{extra}',err=False)
        elif kind=='error':
            typer.echo(f'      ERROR: {event["message"]}',err=True)
    try:
        with database(db) as con:
            stats=scan(con,folder,online,progress=report)
    except (OSError,ValueError) as exc:
        typer.echo(f'Scan failed: {exc}',err=True)
        raise typer.Exit(1)
    typer.echo(f'Scan complete in {time.monotonic()-started:.1f}s: '+', '.join(f'{k}={v}' for k,v in stats.items()))
@app.command()
def serve(db:Path=typer.Option(DEFAULT,'--db'),host:str=typer.Option('127.0.0.1','--host'),port:int=typer.Option(8787,'--port')):
    """Start local dashboard; use --host 0.0.0.0 for trusted LAN phone access."""
    import uvicorn
    from .webapp import create_app
    with database(db):pass
    if host not in ('127.0.0.1','localhost','::1'):
        typer.echo('WARNING: No authentication. Expose only to a trusted private LAN; never port-forward to the internet.',err=True)
    uvicorn.run(create_app(db),host=host,port=port)
@app.command('export')
def export_cmd(format:str=typer.Argument(...,help='json, goodreads or storygraph'),output:Path=typer.Argument(...),db:Path=typer.Option(DEFAULT,'--db')):
    """Export a complete JSON archive or Goodreads/StoryGraph-compatible CSV."""
    with database(db) as con:
        if format.lower()=='json': count=export_json(con,output)
        elif format.lower() in ('goodreads','storygraph','csv'):count=export_csv(con,output)
        else:raise typer.BadParameter('Format must be json, goodreads or storygraph')
    typer.echo(f'Exported {count} books to {output}')
@app.command()
def stats(db:Path=typer.Option(DEFAULT,'--db')):
    """Print catalog statistics."""
    with database(db) as con:
        for label,sql in [('books','SELECT count(*) FROM books'),('files','SELECT count(*) FROM files'),('metadata reviews','SELECT count(*) FROM review_queue WHERE resolved=0'),('reading sessions','SELECT count(*) FROM reading_sessions')]:
            typer.echo(f'{label}: {con.execute(sql).fetchone()[0]}')
@app.command()
def review(db:Path=typer.Option(DEFAULT,'--db'),host:str='127.0.0.1',port:int=8787):
    """Start website with metadata and reading review queues."""
    serve(db,host,port)
if __name__=='__main__':app()

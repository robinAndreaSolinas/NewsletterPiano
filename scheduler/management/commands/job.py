from django.core.management.base import BaseCommand
import logging
from scheduler.job_registry import JobRegistry

logging.disable(logging.WARNING)

class Command(BaseCommand):
    help = 'Base command to manage jobs'

    def add_arguments(self, parser):
        # parser.add_argument('-v','--verbosity', action='count', default=1, help='Verbosity level')
        subparsers = parser.add_subparsers(dest='subcommand')

        list_parser = subparsers.add_parser('list', help='Elenca tutti i job registrati')
        list_parser.add_argument('--name', type=str, help='Filtra per nome')
        list_parser.add_argument('--trigger', type=str, help='Filtra per trigger')
        list_parser.add_argument('--hash', type=str, help='Filtra per id')
        list_parser.add_argument('-l', '--line-number', action='store_true', help='Mostra numero di riga', )

        execute = subparsers.add_parser('run', help='Esegui uno o più job')
        execute.add_argument('job', type=str, help='Hash, nome o pacchetto del job da eseguire', default=None, nargs='?')
        execute.add_argument('--all', action='store_true', help='Esegue tutti i job')
        execute.add_argument('-l', '--line-number', type=int, help='Esegue il job di una riga', )


    def list_jobs(self, options, jobs):
        count = 0
        show_line = options.get('line_number')
        verbose = options.get('verbosity') != 1

        # larghezza hash dinamica
        W = {
            'line': 4,
            'hash': max(max((len(j.id) if verbose else 8) for j in jobs) + 2, 20),
            'name': max(max(len(j.name) for j in jobs) + 2, 20),
            'trigger': max(max(len(j.trigger) for j in jobs) + 2, 20),
        }

        # header
        prefix = ''.ljust(W['line']) if show_line else ''
        self.stdout.write(
            f"{prefix}"
            f"{'HASH'.ljust(W['hash'])}"
            f"{'FUNCTION'.ljust(W['name'])}"
            f"{'TRIGGER'.ljust(W['trigger'])}"
            f"KWARGS"
        )

        for j in jobs:
            if ((options.get('name') and options['name'] not in j.name) or
                    (options.get('trigger') and options['trigger'] not in j.trigger) or
                    (options.get('hash') and options['hash'] not in j.id)):
                continue

            count += 1
            hash_str = j.id if verbose else j.id[:8]

            prefix = str(count).ljust(W['line']) if show_line else ''
            self.stdout.write(
                f"{prefix}"
                f"{hash_str.ljust(W['hash'])}"
                f"{j.name.ljust(W['name'])}"
                f"{j.trigger.ljust(W['trigger'])}"
                f"{j.kwargs}"
            )


    def run_job(self, options, jobs):
        runner_job = set()

        if options['all']:
            for j in jobs:
                runner_job.add(j)
        elif options['job']:
            for j in jobs:
                if (
                    options['job'] == j.name
                    or options['job'][:8] == j.id[:8]
                    or options['job'] == j.id
                    or options['job'] == j.function.__module__.split(".")[0]
                ):
                    runner_job.add(j)

        elif options['line_number']:
            runner_job.add(list(jobs)[options['line_number'] - 1])

        if not runner_job:
            self.stderr.write("No jobs found")
            return

        self.stdout.write(f"Running job")
        for j in runner_job:
            self.stdout.write(f"\t<{j.name} {f"{j.id!r}" if options.get('verbosity') != 1 else f"{j.id[:8]!r}"}>")
            j.function()

    def handle(self, *args, **options):

        jobs = JobRegistry.get()

        match options['subcommand']:

            case 'list':
                self.list_jobs(options, jobs)
            case 'run':
                self.run_job(options, jobs)
            case _:
                self.print_help('manage.py', 'job')
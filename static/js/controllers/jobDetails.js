(function(){
  'use strict';

  define([
      'app',
      'utils/chartHelpers',
      'utils/duration',
      'utils/escapeHtml',
      'directives/radialProgressBar',
      'directives/timeSince',
      'directives/duration',
      'filters/escape',
      'filters/wordwrap',
      'modules/pagination'], function(app, chartHelpers, duration, escapeHtml) {
    app.controller('jobDetailsCtrl', [
        '$scope', '$rootScope', 'initialData', '$window', '$timeout', '$http', '$routeParams', '$filter', 'stream', 'pagination', 'flash',
        function($scope, $rootScope, initialData, $window, $timeout, $http, $routeParams, $filter, Stream, Pagination, flash) {

      var stream, logSources = {},
          entrypoint = '/api/0/jobs/' + $routeParams.job_id + '/',
          buffer_size = 10000,
          chart_options = {
            tooltipFormatter: function(item) {
              var content = '';

              content += '<h5>';
              content += escapeHtml(item.name);
              content += '<br><small>';
              content += escapeHtml(item.target);
              if (item.author) {
                content += ' &mdash; ' + item.author.name;
              }
              content += '</small>';
              content += '</h5>';
              if (item.status.id == 'finished') {
                content += '<p>Job ' + item.result.name;
                if (item.duration) {
                  content += ' in ' + duration(item.duration);
                }
                content += '</p>';
              } else {
                content += '<p>' + item.status.name + '</p>';
              }

              return content;
            }
          };

      function getFormattedJobMessage(job) {
        return $filter('linkify')($filter('escape')(job.message));
      }

      function getLogSourceEntrypoint(logSourceId) {
        return '/api/0/jobs/' + $scope.job.id + '/logs/' + logSourceId + '/';
      }

      function getTestStatus() {
        if ($scope.job.status.id == "finished") {
          if ($scope.testGroups.length === 0) {
            return "no-results";
          } else {
            return "has-results";
          }
        }
        return "pending";
      }

      function updateJob(data){
        $scope.$apply(function() {
          $scope.job = data;
        });
      }

      function updateBuildLog(data) {
        // Angular isn't intelligent enough to optimize this.
        var $el = $('#log-' + data.source.id + ' > .build-log'),
            item, source_id = data.source.id,
            chars_to_remove, lines_to_remove;

        if ($el.length === 0) {
          // logsource isnt available in viewpane
          return;
        }

        if (!logSources[source_id]) {
          return;
        }

        item = logSources[source_id];
        if (data.offset < item.nextOffset) {
          return;
        }

        item.nextOffset = data.offset + data.size;

        if (item.size > buffer_size) {
          $el.empty();
        } else {
          // determine how much space we need to clear up to append data.size
          chars_to_remove = 0 - (buffer_size - item.size - data.size);

          if (chars_to_remove > 0) {
            // determine the number of actual lines to remove
            lines_to_remove = item.text.substr(0, chars_to_remove).split('\n').length;

            // remove number of lines (accounted by <div>'s)
            $el.find('div').slice(0, lines_to_remove - 1).remove();
          }
        }

        // add each additional new line
        $.each(data.text.split('\n'), function(_, line){
          $el.append($('<div class="line">' + line + '</div>'));
        });

        item.text = (item.text + data.text).substr(-buffer_size);
        item.size = item.text.length;

        if ($el.is(':visible')) {
          var el = $el.get(0);
          el.scrollTop = Math.max(el.scrollHeight, el.clientHeight) - el.clientHeight;
        }
      }

      function updateTestGroup(data) {
        $scope.$apply(function() {
          var updated = false,
              item_id = data.id,
              attr, result, item;

          // TODO(dcramer); we need to refactor all of this logic as its repeated in nealry
          // every stream
          if ($scope.testGroups.length > 0) {
            result = $.grep($scope.testGroups, function(e){ return e.id == item_id; });
            if (result.length > 0) {
              item = result[0];
              for (attr in data) {
                // ignore dateModified as we're updating this frequently and it causes
                // the dirty checking behavior in angular to respond poorly
                if (item[attr] != data[attr] && attr != 'dateModified') {
                  updated = true;
                  item[attr] = data[attr];
                }
                if (updated) {
                  item.dateModified = data.dateModified;
                }
              }
            }
          }
          if (!updated) {
            $scope.testGroups.unshift(data);
          }

          if (data.result.id == 'failed') {
            if ($scope.testFailures.length > 0) {
              result = $.grep($scope.testFailures, function(e){ return e.id == item_id; });
              if (result.length > 0) {
                item = result[0];
                for (attr in data) {
                  // ignore dateModified as we're updating this frequently and it causes
                  // the dirty checking behavior in angular to respond poorly
                  if (item[attr] != data[attr] && attr != 'dateModified') {
                    updated = true;
                    item[attr] = data[attr];
                  }
                  if (updated) {
                    item.dateModified = data.dateModified;
                  }
                }
              }
            }
            if (!updated) {
              $scope.testFailures.unshift(data);
            }
          }
        });
      }

      $scope.retryJob = function() {
        $http.post('/api/0/jobs/' + $scope.job.id + '/retry/')
          .success(function(data){
            $window.location.href = data.build.link;
          })
          .error(function(){
            flash('error', 'There was an error while retrying this job.');
          });
      };

      $scope.$watch("job.status", function() {
        $scope.testStatus = getTestStatus();
      });
      $scope.$watch("job.message", function() {
        $scope.formattedJobMessage = getFormattedJobMessage($scope.job);
      });
      $scope.$watch("tests", function() {
        $scope.testStatus = getTestStatus();
      });
      $scope.$watch("logSources", function(){
        $timeout(function(){
          $('#log_sources a[data-toggle="tab"]').tab();
          $('#log_sources a[data-toggle="tab"]').on('show.bs.tab', function(e){
            var source_id = $(e.target).attr("data-source"),
                $el = $(e.target).attr("href");

            if (!logSources[source_id]) {
              logSources[source_id] = {
                text: '',
                size: 0,
                nextOffset: 0
              };

              $http.get(getLogSourceEntrypoint(source_id) + '?limit=' + buffer_size)
                .success(function(data){
                  $.each(data.chunks, function(_, chunk){
                    updateBuildLog(chunk);
                  });
                  $("#log_sources").tab();
                });
            } else {
              $el.tab('show');
            }
          });
          $('#log_sources a[data-toggle="tab"]:first').tab("show");
        });
      });

      $scope.project = initialData.data.project;
      $scope.job = initialData.data.build;
      $scope.logSources = initialData.data.logs;
      $scope.phases = initialData.data.phases;
      $scope.testFailures = initialData.data.testFailures;
      $scope.testGroups = initialData.data.testGroups;
      $scope.previousRuns = initialData.data.previousRuns;
      $scope.chartData = chartHelpers.getChartData($scope.previousRuns, $scope.job, chart_options);

      $rootScope.activeProject = $scope.project;


      // TODO: we need to support multiple soruces, a real-time stream, and real-time source changes
      stream = new Stream($scope, entrypoint);
      stream.subscribe('job.update', updateJob);
      stream.subscribe('buildlog.update', updateBuildLog);
      stream.subscribe('testgroup.update', updateTestGroup);
    }]);
  });
})();
